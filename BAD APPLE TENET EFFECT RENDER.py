import cv2
import numpy as np
import os
import sys
import time
import re
import shutil
import subprocess

# ==========================================
# UTILITIES (Outside of classes)
# ==========================================

def get_key_nonblocking():
    """Checks for a key press without blocking the main program execution."""
    if os.name == 'nt':  # Windows
        import msvcrt
        # Check if a key has been pressed
        if msvcrt.kbhit():
            return msvcrt.getch().decode('utf-8', errors='ignore').lower()
        return None
    else:  # Linux / macOS
        import select, termios, tty
        try:
            # Save current terminal settings
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            # Enable raw mode for immediate character reading
            tty.setraw(fd)
            # Check if input is available
            if select.select([sys.stdin], [], [], 0.0)[0]:
                char = sys.stdin.read(1).lower()
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                return char
            # Restore terminal settings
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            return None
        except Exception:
            return None


# ==========================================
# CLASS 1: MENU (Interface and State Management)
# ==========================================

class Menu:
    def __init__(self):
        """Initializes the menu state machine and default configuration flags."""
        self.current_section_link = self.section_file_select
        self.exit_program = False
        self.render_requested = False
        
        self.selected_file = None
        self.modes = {'time': False, 'h_flip': False, 'color': False}
        self.reverse_audio = False
        self.source_color_stops = None
        self.target_color_stops = None

    def validate_file(self):
        """Checks if the selected file still exists. Returns False if missing."""
        if not self.selected_file or not os.path.exists(self.selected_file):
            print("\n" + "="*60)
            print(" ⚠️ CRITICAL ERROR: FILE NOT FOUND ")
            print("="*60)
            print(f" The file '{self.selected_file}' was deleted, moved, or renamed!")
            print(" Returning to file selection menu...\n")
            return False
        return True

    def choose_menu_point(self):
        """Main entry point for ProcessManager. Executes current section and updates state."""
        next_section = self.current_section_link()
        if next_section is not None:
            self.current_section_link = next_section
        return next_section

    def section_file_select(self):
        """File selection menu with safe, non-recursive directory refreshing."""
        while True:
            valid_extensions = ('.mp4', '.avi', '.mkv', '.mov', '.webm')
            # Re-scan directory on every loop iteration to prevent stale data
            files = [f for f in os.listdir('.') if f.lower().endswith(valid_extensions)]
            
            # Handle empty directory gracefully
            if not files:
                print("\n" + "="*60)
                print(" ⚠️ WARNING: No video files found in the directory! ")
                print(" Please add a video file, then press Enter to refresh...")
                input("="*60)
                continue
            
            print("\n" + "="*60)
            print(" 📁 SELECT SOURCE FILE")
            print("="*60)
            for i, f in enumerate(files, 1):
                print(f"  [{i}] {f}")
            
            print("  [r] 🔄 REFRESH FILE LIST (Update directory state)")
            print("  [0] 🚪 EXIT PROGRAM")
            
            choice = input("\n👉 Enter file number, 'r' to refresh, or 0 to exit: ").strip().lower()
            parts = choice.split()
            
            # STRICT VALIDATION: Prevent mixing '0' or 'r' with file selections
            if len(parts) > 1 and ('0' in parts or 'r' in parts):
                print("⚠️ Error: Cannot mix '0' or 'r' with file number selections.")
                continue
                
            if choice == '0':
                self.exit_program = True
                return None
            elif choice == 'r':
                continue  # Instantly restart loop to re-read directory
            else:
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(files):
                        self.selected_file = files[idx]
                        return self.section_modes  # Transition to next state
                    print("⚠️ Error: Number out of range.")
                except ValueError:
                    print("⚠️ Error: Please enter a valid number or 'r'.")

    def section_modes(self):
        """Video processing modes selection menu."""
        if not self.validate_file():
            return self.section_file_select  # Fallback if file disappeared

        print("\n" + "="*60)
        print(" ⚙️  SELECT VIDEO PROCESSING MODES")
        print("="*60)
        print("  [1] Reverse Time")
        print("  [2] Mirror Horizontal")
        print("  [3] Color Gradient Mapping (Source → Target)")
        print("  [0] ⬅️  GO BACK TO FILE SELECTION")
        
        while True:
            choice = input("\n👉 Enter mode numbers separated by space (or 0 to go back): ").strip()
            parts = choice.split()
            
            # STRICT VALIDATION: Prevent mixing '0' (go back) with actual mode selections
            if '0' in parts and len(parts) > 1:
                print("⚠️ Error: Cannot mix '0' (go back) with other mode selections.")
                continue
            
            # WARNING: Detect duplicate menu selections
            if len(parts) > 1 and len(parts) != len(set(parts)):
                print("⚠️ Warning: Duplicate menu selections detected. Proceeding with unique choices.")
                
            if choice == '0':
                return self.section_file_select
            
            try:
                # Use set() to automatically deduplicate valid choices
                modes = list(set(int(x) for x in parts))
                if all(0 <= m <= 3 for m in modes):
                    if 0 in modes:
                        self.modes = {'time': False, 'h_flip': False, 'color': False}
                    else:
                        self.modes = {
                            'time': 1 in modes,
                            'h_flip': 2 in modes,
                            'color': 3 in modes
                        }
                    return self.section_audio
                print("⚠️ Error: Only digits 0 to 3 are allowed.")
            except ValueError:
                print("⚠️ Error: Enter only digits separated by spaces.")

    def section_audio(self):
        """Audio track reversal settings menu."""
        if not self.validate_file():
            return self.section_file_select

        print("\n" + "="*60)
        print(" 🔊 AUDIO TRACK SETTINGS")
        print("="*60)
        print("  Do you want to reverse the audio track?")
        print("  [y] Yes, reverse audio (Tenet style)")
        print("  [n] No, keep audio as is")
        print("  [0] or 'back' ⬅️ GO BACK TO MODE SELECTION")
        
        while True:
            choice = input("\n👉 Your choice (y/n/0): ").strip().lower()
            parts = choice.split()
            
            # STRICT VALIDATION: Prevent mixing '0'/'back' with 'y'/'n'
            if len(parts) > 1 and ('0' in parts or 'back' in parts):
                print("⚠️ Error: Cannot mix '0' or 'back' with other choices.")
                continue
                
            if choice in ['0', 'back']:
                return self.section_modes
            elif choice in ['y', 'yes']:
                self.reverse_audio = True
                return self.section_color if self.modes['color'] else self._request_render()
            elif choice in ['n', 'no']:
                self.reverse_audio = False
                return self.section_color if self.modes['color'] else self._request_render()
            else:
                print("⚠️ Error: Enter 'y', 'n', or '0' to go back.")

    def _get_single_scale(self, prompt_title, prompt_example):
        """Universal helper to parse and validate a single multi-zone color scale."""
        print("\n" + "="*60)
        print(f" 🎨 {prompt_title}")
        print("="*60)
        print(f"  Format: percent(r,g,b) separated by space.")
        print(f"  Example: {prompt_example}")
        print("  [0] or 'back' ⬅️ GO BACK")
        
        pattern = re.compile(r'^(\d+)\((\d+),(\d+),(\d+)\)$')
        
        while True:
            user_input = input("\n👉 Enter scale: ").strip().lower()
            parts = user_input.split()
            
            # STRICT VALIDATION: Prevent mixing '0'/'back' with actual scale data
            if len(parts) > 1 and ('0' in parts or 'back' in parts):
                print("⚠️ Error: Cannot mix '0' or 'back' with scale definitions.")
                continue
                
            if user_input in ['0', 'back']:
                return None
                
            errors = []
            
            if not parts:
                print("⚠️ Error: Input cannot be empty.")
                continue
                
            parsed_stops = []
            for part in parts:
                match = pattern.match(part)
                if not match:
                    errors.append(f"Invalid format '{part}'. Expected: number(r,g,b)")
                else:
                    parsed_stops.append((int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))))
            
            if errors:
                print("\n⚠️ Format errors found:")
                for err in errors: print(f"  ❌ {err}")
                print("  💡 Tip: Do not put spaces inside parentheses.\n")
                continue
                
            # Logical validation rules for color scales
            if parsed_stops[0][0] != 0:
                errors.append("First number (percent) must always be 0.")
            if parsed_stops[-1][0] != 100:
                errors.append("Last number (percent) must always be 100.")
            for i in range(1, len(parsed_stops)):
                if parsed_stops[i][0] <= parsed_stops[i-1][0]:
                    errors.append(f"Percent {parsed_stops[i][0]} must be strictly greater than previous ({parsed_stops[i-1][0]}).")
            for pct, r, g, b in parsed_stops:
                if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
                    errors.append(f"At {pct}%, RGB values must be in the range 0-255.")
            
            if errors:
                print("\n⚠️ The following errors were found:")
                for err in errors: print(f"  ❌ {err}")
                print("Please correct the input.\n")
            else:
                return parsed_stops

    def section_color(self):
        """Menu for inputting BOTH source and target color scales."""
        if not self.validate_file():
            return self.section_file_select

        # Step 1: Get source scale
        source_stops = self._get_single_scale(
            "SOURCE COLOR SCALE (What to replace)",
            "0(255,0,0) 100(0,0,255)"
        )
        if source_stops is None:
            return self.section_audio
        
        # Step 2: Get target scale
        target_stops = self._get_single_scale(
            "TARGET COLOR SCALE (What to replace with)",
            "0(0,0,0) 100(255,255,255)"
        )
        if target_stops is None:
            return self.section_audio
        
        self.source_color_stops = source_stops
        self.target_color_stops = target_stops
        
        print("\n✅ Both color scales are valid and ready for mapping.")
        return self._request_render()

    def _request_render(self):
        """Helper method to signal the ProcessManager that rendering can begin."""
        self.render_requested = True
        return None

    def post_render_menu(self):
        """Menu displayed after a render completes or is aborted."""
        print("\n" + "="*60)
        print(" 🔄 POST-RENDER ACTIONS")
        print("="*60)
        while True:
            choice = input("\n🔄 What's next?\n  [1] Load a new file\n  [2] Different settings for THIS file\n  [0] Exit program\n👉 Your choice: ").strip()
            parts = choice.split()
            
            # STRICT VALIDATION: Prevent mixing '0' (exit) with '1' or '2'
            if len(parts) > 1 and '0' in parts:
                print("⚠️ Error: Cannot mix '0' (exit) with other action choices.")
                continue
            
            # WARNING: Detect duplicate menu selections
            if len(parts) > 1 and len(parts) != len(set(parts)):
                print("⚠️ Warning: Duplicate menu selections detected. Proceeding with unique choices.")
                
            if choice == '0':
                self.exit_program = True
                break
            elif choice == '1':
                self.current_section_link = self.section_file_select
                break
            elif choice == '2':
                self.current_section_link = self.section_modes
                break
            else:
                print("⚠️ Enter 0, 1, or 2.")


# ==========================================
# CLASS 2: RENDER (Pure Backend and Drawing)
# ==========================================

class Render:
    def __init__(self):
        """Initializes rendering state variables."""
        self.abort_state = 0

    def print_pipeline_header(self, suffixes):
        """Prints the standard, identical header before any progress bar."""
        modes_str = ", ".join(suffixes) if suffixes else "None"
        print(f"🎯 Active modes: {modes_str}")
        print("💡 Tip: Press 'Q' at any time to request abort.")
        print("🚀 Starting pipeline:")

    def taskbar(self, current, total, start_time, abort_state, bar_width=50):
        """
        Draws the universal TENET-style reverse progress bar.
        ALWAYS right-to-left, decreasing percentage, with stats, ETA, and abort prompt.
        """
        if not total: return
        
        # TENET style: 100% at start, 0% at end, filling from right to left
        reverse_ratio = 1.0 - (current / total)
        percentage = int(reverse_ratio * 100)
        filled = int(reverse_ratio * bar_width)
        bar_str = '█' * filled + '░' * (bar_width - filled)
        
        # Calculate speed and ETA
        elapsed = time.time() - start_time
        speed = current / elapsed if elapsed > 0.1 else 0.0
        eta = (total - current) / speed if speed > 0 else 0
        
        h, rem = divmod(int(eta), 3600)
        m, s = divmod(rem, 60)
        eta_str = f"{h}h {m:02d}m {s:02d}s" if h > 0 else f"{m:02d}m {s:02d}s"
        
        # Format output string based on abort state
        if abort_state == 0:
            line = f"\r{percentage:3d}% - [{bar_str}] | {speed:5.1f} fps | ETA: {eta_str} | [Q=abort]"
        else:
            line = f"\r{percentage:3d}% - [{bar_str}] | ⚠️ CONFIRM ABORT (y/n): "
            
        sys.stdout.write(line)
        sys.stdout.flush()

    def apply_mirror(self, frame):
        """Applies horizontal mirroring to the frame."""
        return cv2.flip(frame, 1)

    def apply_color_mapping(self, frame, source_stops, target_stops):
        """Maps pixel colors from source gradient zones to target gradient zones."""
        # 1. Align target scale percentages to match the source scale
        source_pcts = [stop[0] for stop in source_stops]
        target_pcts = [stop[0] for stop in target_stops]
        
        target_r = [stop[1] for stop in target_stops]
        target_g = [stop[2] for stop in target_stops]
        target_b = [stop[3] for stop in target_stops]
        
        # Interpolate target colors to match source percentage points
        aligned_r = np.interp(source_pcts, target_pcts, target_r)
        aligned_g = np.interp(source_pcts, target_pcts, target_g)
        aligned_b = np.interp(source_pcts, target_pcts, target_b)
        
        aligned_target_stops = [
            (source_pcts[i], int(aligned_r[i]), int(aligned_g[i]), int(aligned_b[i]))
            for i in range(len(source_stops))
        ]
        
        # 2. Apply vector projection mapping
        result = frame.copy().astype(np.float32)
        
        for i in range(len(source_stops) - 1):
            src_start = np.array([source_stops[i][1], source_stops[i][2], source_stops[i][3]], dtype=np.float32)
            src_end = np.array([source_stops[i+1][1], source_stops[i+1][2], source_stops[i+1][3]], dtype=np.float32)
            
            tgt_start = np.array([aligned_target_stops[i][1], aligned_target_stops[i][2], aligned_target_stops[i][3]], dtype=np.float32)
            tgt_end = np.array([aligned_target_stops[i+1][1], aligned_target_stops[i+1][2], aligned_target_stops[i+1][3]], dtype=np.float32)
            
            src_direction = src_end - src_start
            direction_length_sq = np.sum(src_direction * src_direction)
            
            if direction_length_sq < 1e-6:
                continue  # Skip if points are identical
            
            # Project pixel colors onto the source direction vector
            pixel_vector = frame.astype(np.float32) - src_start
            dot_product = np.sum(pixel_vector * src_direction, axis=2)
            t = np.clip(dot_product / direction_length_sq, 0, 1)
            
            # Interpolate target color based on projection ratio 't'
            interpolated_color = tgt_start + t[:, :, np.newaxis] * (tgt_end - tgt_start)
            mask = (t > 0) & (t < 1)
            result[mask] = interpolated_color[mask]
        
        return np.clip(result, 0, 255).astype(np.uint8)

    def process_audio_ffmpeg(self, input_video, silent_video, final_output, reverse_audio):
        """Extracts, optionally reverses, and merges audio using FFmpeg."""
        if not shutil.which("ffmpeg"):
            print("\n⚠️ CRITICAL WARNING: FFmpeg not found in system!")
            print("   Audio track will not be added. Video saved without sound.")
            return silent_video

        temp_wav = "temp_audio_extract.wav"
        temp_rev_wav = "temp_audio_reversed.wav"

        print("🔊 Extracting audio track from original source...")
        res = subprocess.run(["ffmpeg", "-y", "-i", input_video, "-vn", "-acodec", "pcm_s16le", temp_wav], 
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if res.returncode != 0 or not os.path.exists(temp_wav) or os.path.getsize(temp_wav) < 1000:
            print("ℹ️ No audio track detected in source video. Saving silent video.")
            if os.path.exists(temp_wav): os.remove(temp_wav)
            return silent_video

        audio_to_mux = temp_wav
        if reverse_audio:
            print("⏪ Reversing audio track...")
            subprocess.run(["ffmpeg", "-y", "-i", temp_wav, "-af", "areverse", temp_rev_wav],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            audio_to_mux = temp_rev_wav

        print("🔗 Merging processed video and audio...")
        subprocess.run([
            "ffmpeg", "-y", "-i", silent_video, "-i", audio_to_mux, 
            "-c:v", "copy", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0", final_output
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Cleanup temporary files
        if os.path.exists(silent_video): os.remove(silent_video)
        if os.path.exists(temp_wav): os.remove(temp_wav)
        if os.path.exists(temp_rev_wav): os.remove(temp_rev_wav)
        
        print("✅ Audio successfully processed and merged!")
        return final_output

    def run_pipeline(self, input_video, modes, reverse_audio, source_stops, target_stops):
        """Main streaming render pipeline. Executes selected modes frame-by-frame."""
        # Final safety check right before processing
        if not os.path.exists(input_video):
            print("\n" + "="*60)
            print(" ⚠️ CRITICAL ERROR: FILE DISAPPEARED DURING SETUP ")
            print("="*60)
            print(f" The file '{input_video}' is no longer accessible.")
            print(" Aborting render and returning to file selection.\n")
            return "FILE_MISSING"

        # Generate output filenames
        suffixes = []
        if modes['time']: suffixes.append("REVERSED")
        if modes['h_flip']: suffixes.append("MIRRORED")
        if modes['color']: suffixes.append("COLORMAPPED")
        if reverse_audio: suffixes.append("AUDIO_REV")
        
        suffix = "_" + "_".join(suffixes) if suffixes else "_PROCESSED"
        name, ext = os.path.splitext(input_video)
        
        silent_output = f"{name}{suffix}_SILENT{ext}"
        final_output = f"{name}{suffix}_WITH_AUDIO{ext}"
        
        working_video = input_video
        temp_reversed_file = None
        
        # Pre-process: Reverse video on disk if requested (Memory-Safe with TENET Progress Bar)
        if modes['time']:
            print("\n⏪ Reversing video timeline via FFmpeg (Memory-Safe Mode)...")
            temp_reversed_file = "temp_reversed_source.mp4"
            
            # Probe total frames for accurate progress calculation
            cap_probe = cv2.VideoCapture(input_video)
            total_rev_frames = int(cap_probe.get(cv2.CAP_PROP_FRAME_COUNT))
            cap_probe.release()
            
            # Build FFmpeg command
            cmd = [
                "ffmpeg", "-y", "-i", input_video, "-vf", "reverse", "-an", 
                "-c:v", "libx264", "-preset", "ultrafast", temp_reversed_file
            ]
            
            # Print the IDENTICAL header before the FFmpeg progress bar
            self.print_pipeline_header(suffixes)
            
            # Run FFmpeg and capture stderr for real-time progress tracking
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.PIPE, 
                text=True, 
                encoding='utf-8', 
                errors='ignore'
            )
            
            start_time = time.time()
            current_frame = 0
            ffmpeg_abort_state = 0
            
            # Read stderr line by line to parse frame count
            while True:
                # Non-blocking abort check for FFmpeg process
                key = get_key_nonblocking()
                if key == 'q' and ffmpeg_abort_state == 0:
                    ffmpeg_abort_state = 1
                
                if ffmpeg_abort_state == 1:
                    if key == 'y':
                        process.terminate()
                        ffmpeg_abort_state = 2
                        break
                    elif key == 'n':
                        ffmpeg_abort_state = 0
                
                line = process.stderr.readline()
                if not line:
                    if process.poll() is not None:
                        break
                    continue
                
                # Parse frame number from FFmpeg output
                match = re.search(r'frame=\s*(\d+)', line)
                if match:
                    current_frame = int(match.group(1))
                    # Use the EXACT SAME taskbar function (TENET style)
                    self.taskbar(current_frame, total_rev_frames, start_time, ffmpeg_abort_state)
            
            # Ensure the progress bar reaches 100% upon successful completion
            if ffmpeg_abort_state != 2 and total_rev_frames > 0:
                self.taskbar(total_rev_frames, total_rev_frames, start_time, 0)
            print("\n") # Newline after progress bar
            
            if ffmpeg_abort_state == 2:
                print("⚠️ FFMPEG REVERSAL ABORTED BY USER.")
                # Cleanup partial file if it exists
                if os.path.exists(temp_reversed_file):
                    os.remove(temp_reversed_file)
                return "ABORTED"
            
            if os.path.exists(temp_reversed_file):
                working_video = temp_reversed_file
                print("✅ Video reversed on disk successfully. Zero RAM used.")
            else:
                print("⚠️ FFmpeg reversal failed. Proceeding with original.")

        # Initialize VideoCapture and VideoWriter for main render
        cap = cv2.VideoCapture(working_video)
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0: total_frames = None
            
        out = cv2.VideoWriter(silent_output, cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))
        
        print(f"\n⏳ Initializing streaming render: {width}x{height}, {fps} FPS")
        # Print the IDENTICAL header before the main render progress bar
        self.print_pipeline_header(suffixes)
        
        start_time = time.time()
        frame_idx = 0
        self.abort_state = 0
        
        # Main streaming loop
        while True:
            ret, frame = cap.read()
            if not ret: break
            
            # Non-blocking abort check
            key = get_key_nonblocking()
            if key == 'q' and self.abort_state == 0: self.abort_state = 1
            if self.abort_state == 1:
                if key == 'y':
                    self.abort_state = 2
                    break
                elif key == 'n': self.abort_state = 0
            if self.abort_state == 2: break
            
            processed_frame = frame.copy()
            
            # Apply selected rendering modes
            if modes['h_flip']:
                processed_frame = self.apply_mirror(processed_frame)
            if modes['color'] and source_stops and target_stops:
                processed_frame = self.apply_color_mapping(processed_frame, source_stops, target_stops)
            
            out.write(processed_frame)
            frame_idx += 1
            
            # Update TENET-style REVERSE progress bar for main rendering
            self.taskbar(frame_idx, total_frames, start_time, self.abort_state)
        
        print("\n")
        cap.release()
        out.release()
        
        # Cleanup temporary reversed video file
        if temp_reversed_file and os.path.exists(temp_reversed_file): os.remove(temp_reversed_file)
        
        if self.abort_state == 2 or 'ffmpeg_abort_state' in locals() and ffmpeg_abort_state == 2:
            print("⚠️ VIDEO RENDER ABORTED BY USER.")
            return "ABORTED"
        else:
            print("✅ VIDEO PROCESSING COMPLETED!")
            self.process_audio_ffmpeg(input_video, silent_output, final_output, reverse_audio)
            print("="*60)
            print(f"🎉 FULL PROCESSING SUCCESSFULLY COMPLETED! Final file: {final_output}")
            print("="*60)
            
        return "SUCCESS"


# ==========================================
# CLASS 3: PROCESS MANAGER (Orchestrator)
# ==========================================

class ProcessManager:
    def __init__(self):
        """Initializes Menu and Render objects, and runs the main control loop."""
        print("="*60)
        print(" 🌀 UNIVERSAL TENET VIDEO CONSTRUCTOR (v11.0 Final Polish) 🌀 ")
        print("="*60)
        
        self.menu = Menu()
        self.render = Render()
        
        while True:
            # Condition 1: Run menu until render is requested or exit is triggered
            while not self.menu.render_requested and not self.menu.exit_program:
                self.menu.choose_menu_point()
                
            # Condition 2: Safe global exit check
            if self.menu.exit_program:
                print("\n👋 Exiting program. See you!")
                break
                
            # Condition 1 (continued): Execute render if requested
            if self.menu.render_requested:
                result = self.render.run_pipeline(
                    self.menu.selected_file,
                    self.menu.modes,
                    self.menu.reverse_audio,
                    self.menu.source_color_stops,
                    self.menu.target_color_stops
                )
                
                # Handle edge cases: file vanished or user aborted
                if result in ["FILE_MISSING", "ABORTED"]:
                    self.menu.current_section_link = self.menu.section_file_select
                    self.menu.render_requested = False
                    continue
                
                # Reset flag and show post-render options
                self.menu.render_requested = False
                self.menu.post_render_menu()

# ==========================================
# ENTRY POINT
# ==========================================
if __name__ == "__main__":
    # Instantiating ProcessManager automatically triggers __init__ and starts the app
    ProcessManager()