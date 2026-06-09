import cv2
import numpy as np
import os
import sys
import time
import re
import shutil
import subprocess

# ==========================================
# 1. UTILITIES AND NON-BLOCKING INPUT
# ==========================================

def get_key_nonblocking():
    """Checks for key press without blocking program execution."""
    if os.name == 'nt':  # Windows
        import msvcrt
        if msvcrt.kbhit():
            return msvcrt.getch().decode('utf-8', errors='ignore').lower()
        return None
    else:  # Linux / macOS
        import select, sys, termios, tty
        try:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            tty.setraw(fd)
            if select.select([sys.stdin], [], [], 0.0)[0]:
                char = sys.stdin.read(1).lower()
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                return char
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            return None
        except Exception:
            return None

def update_tenet_progress(frames_processed, total_frames, start_time, abort_state, bar_width=50):
    """Universal TENET-style reverse progress bar."""
    if not total_frames:
        return
        
    reverse_ratio = 1.0 - (frames_processed / total_frames)
    percentage = int(reverse_ratio * 100)
    filled = int(reverse_ratio * bar_width)
    empty = bar_width - filled
    bar_str = '█' * filled + '░' * empty
    
    elapsed_sec = time.time() - start_time
    if elapsed_sec > 0.1:
        speed_fps = frames_processed / elapsed_sec
    else:
        speed_fps = 0.0
        
    remaining_frames = total_frames - frames_processed
    if speed_fps > 0:
        eta_sec = remaining_frames / speed_fps
    else:
        eta_sec = 0.0
        
    hours = int(eta_sec // 3600)
    minutes = int((eta_sec % 3600) // 60)
    seconds = int(eta_sec % 60)
    
    if hours > 0:
        eta_str = f"{hours}h {minutes:02d}m {seconds:02d}s"
    else:
        eta_str = f"{minutes:02d}m {seconds:02d}s"
    
    if abort_state == 0:
        progress_line = f"\r{percentage:3d}% - [{bar_str}] | {speed_fps:5.1f} fps | ETA: {eta_str} | [Q=abort]"
    else:
        progress_line = f"\r{percentage:3d}% - [{bar_str}] | ⚠️ CONFIRM ABORT (y/n): "
    
    sys.stdout.write(progress_line)
    sys.stdout.flush()

def get_valid_video_file():
    valid_extensions = ('.mp4', '.avi', '.mkv', '.mov', '.webm')
    files = [f for f in os.listdir('.') if f.lower().endswith(valid_extensions)]
    
    if not files:
        print("❌ Error: No video files found in the script directory!")
        sys.exit()

    print("\n" + "="*60)
    print(" 📁 SELECT SOURCE FILE")
    print("="*60)
    for i, f in enumerate(files, 1):
        print(f"  [{i}] {f}")
    print("  [0] 🚪 EXIT PROGRAM")

    while True:
        choice = input("\n👉 Enter file number (or 0 to exit): ").strip()
        if choice == '0':
            print("\n👋 Exiting program. See you!")
            sys.exit()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(files):
                return files[idx]
            print("⚠️ Error: Number out of range.")
        except ValueError:
            print("⚠️ Error: Please enter a valid number.")

def get_transformation_modes():
    print("\n" + "="*60)
    print(" ⚙️  SELECT VIDEO PROCESSING MODES")
    print("="*60)
    print("  [1] Reverse Time")
    print("  [2] Mirror Horizontal")
    print("  [3] Multi-zone Color Gradient")
    print("  [0] ⬅️  GO BACK TO FILE SELECTION")
    
    while True:
        choice = input("\n👉 Enter mode numbers separated by space (or 0 to go back): ").strip()
        if choice == '0':
            return None
        
        try:
            modes = [int(x) for x in choice.split()]
            if all(0 <= m <= 3 for m in modes):
                if 0 in modes:
                    return {'time': False, 'h_flip': False, 'color': False}
                return {
                    'time': 1 in modes,
                    'h_flip': 2 in modes,
                    'color': 3 in modes
                }
            print("⚠️ Error: Only digits 0 to 3 are allowed.")
        except ValueError:
            print("⚠️ Error: Enter only digits separated by spaces.")

def get_audio_reversal_mode():
    print("\n" + "="*60)
    print(" 🔊 AUDIO TRACK SETTINGS")
    print("="*60)
    print("  Do you want to reverse the audio track?")
    print("  [y] Yes, reverse audio (Tenet style)")
    print("  [n] No, keep audio as is")
    print("  [0] or 'back' ⬅️ GO BACK TO MODE SELECTION")
    
    while True:
        choice = input("\n👉 Your choice (y/n/0): ").strip().lower()
        if choice in ['0', 'back']:
            return None
        elif choice in ['y', 'yes']:
            return True
        elif choice in ['n', 'no']:
            return False
        else:
            print("⚠️ Error: Enter 'y', 'n', or '0' to go back.")

def get_color_scale_input():
    print("\n" + "="*60)
    print(" 🎨 MULTI-ZONE COLOR SCALE SETTINGS")
    print("="*60)
    print("  Format: percent(r,g,b) separated by space.")
    print("  Example: 0(0,0,127) 50(255,0,0) 100(0,255,0)")
    print("  [0] or 'back' ⬅️ GO BACK TO AUDIO SETTINGS")
    
    pattern = re.compile(r'^(\d+)\((\d+),(\d+),(\d+)\)$')
    
    while True:
        user_input = input("\n👉 Enter scale: ").strip().lower()
        
        if user_input in ['0', 'back']:
            return None
            
        errors = []
        parts = user_input.split()
        
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

def build_color_lut(stops):
    """Creates a seamless 1D color lookup table (LUT) of size 256x3."""
    x_points = [int(round(pct * 2.55)) for pct, _, _, _ in stops]
    r_points = [r for _, r, _, _ in stops]
    g_points = [g for _, _, g, _ in stops]
    b_points = [b for _, _, _, b in stops]
    
    x_target = np.arange(256)
    r_lut = np.round(np.interp(x_target, x_points, r_points)).astype(np.uint8)
    g_lut = np.round(np.interp(x_target, x_points, g_points)).astype(np.uint8)
    b_lut = np.round(np.interp(x_target, x_points, b_points)).astype(np.uint8)
    
    return np.column_stack((b_lut, g_lut, r_lut))

def process_audio_ffmpeg(input_video, silent_video, final_output, reverse_audio):
    """Processes audio using FFmpeg and merges it with the video."""
    if not shutil.which("ffmpeg"):
        print("\n⚠️ CRITICAL WARNING: FFmpeg not found in system!")
        print("   Audio track will not be added. Video saved without sound.")
        print("   💡 Install FFmpeg and add it to your system PATH for full functionality.")
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
        print("⏪ Reversing audio...")
        subprocess.run(["ffmpeg", "-y", "-i", temp_wav, "-af", "areverse", temp_rev_wav],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        audio_to_mux = temp_rev_wav

    print("🔗 Merging processed video and audio...")
    subprocess.run([
        "ffmpeg", "-y", 
        "-i", silent_video, 
        "-i", audio_to_mux, 
        "-c:v", "copy", 
        "-c:a", "aac", 
        "-map", "0:v:0",  
        "-map", "1:a:0",  
        final_output
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if os.path.exists(silent_video): os.remove(silent_video)
    if os.path.exists(temp_wav): os.remove(temp_wav)
    if os.path.exists(temp_rev_wav): os.remove(temp_rev_wav)
    
    print("✅ Audio successfully processed and merged!")
    return final_output

# ==========================================
# 2. MAIN PROGRAM LOOP
# ==========================================

print("="*60)
print(" 🌀 UNIVERSAL TENET VIDEO CONSTRUCTOR (v6.0 Memory-Safe) 🌀 ")
print("="*60)

while True:
    input_video = get_valid_video_file()
    
    while True:
        modes = get_transformation_modes()
        if modes is None:
            break
        
        while True:
            reverse_audio = get_audio_reversal_mode()
            if reverse_audio is None:
                break
            
            color_lut = None
            skip_to_modes = False
            
            if modes['color']:
                while True:
                    stops = get_color_scale_input()
                    if stops is None:
                        skip_to_modes = True
                        break
                    
                    print("\n✅ Scale is valid. Generating LUT...")
                    color_lut = build_color_lut(stops)
                    print("✅ Color table successfully merged and ready.")
                    break
            
            if skip_to_modes:
                continue
            
            suffixes = []
            if modes['time']: suffixes.append("REVERSED")
            if modes['h_flip']: suffixes.append("MIRRORED")
            if modes['color']: suffixes.append("COLORED")
            if reverse_audio: suffixes.append("AUDIO_REV")
            
            suffix = "_" + "_".join(suffixes) if suffixes else "_PROCESSED"
            name, ext = os.path.splitext(input_video)
            
            silent_output = f"{name}{suffix}_SILENT{ext}"
            final_output = f"{name}{suffix}_WITH_AUDIO{ext}"
            
            # ==========================================
            # MEMORY-SAFE TIME REVERSAL PRE-PROCESSING
            # ==========================================
            working_video = input_video
            temp_reversed_file = None
            
            if modes['time']:
                print("\n⏪ Reversing video timeline via FFmpeg (Memory-Safe Mode)...")
                print("   (Loading 6500+ frames into RAM would cause OutOfMemory error)")
                temp_reversed_file = "temp_reversed_source.mp4"
                
                # Reverse video on disk, drop audio for now (we handle it separately)
                subprocess.run([
                    "ffmpeg", "-y", "-i", input_video, 
                    "-vf", "reverse", 
                    "-an", 
                    "-c:v", "libx264", "-preset", "ultrafast", 
                    temp_reversed_file
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                if os.path.exists(temp_reversed_file):
                    working_video = temp_reversed_file
                    print("✅ Video reversed on disk successfully. Zero RAM used.")
                else:
                    print("⚠️ FFmpeg reversal failed. Proceeding with original (may cause OOM).")

            # ==========================================
            # STREAMING RENDER PIPELINE (NO LISTS!)
            # ==========================================
            cap = cv2.VideoCapture(working_video)
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            if total_frames <= 0: 
                total_frames = None
            
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(silent_output, fourcc, fps, (width, height))
            
            print(f"\n⏳ Initializing streaming render: {width}x{height}, {fps} FPS")
            print(f"🎯 Active modes: {', '.join(suffixes) if suffixes else 'None'}")
            print("💡 Tip: Press 'Q' at any time to request abort.\n")
            print("🚀 Starting processing pipeline:")
            
            start_time = time.time()
            frame_idx = 0
            abort_state = 0
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                key = get_key_nonblocking()
                if key == 'q' and abort_state == 0:
                    abort_state = 1
                if abort_state == 1:
                    if key == 'y':
                        abort_state = 2
                        break
                    elif key == 'n':
                        abort_state = 0
                
                if abort_state == 2:
                    break
                
                processed_frame = frame.copy()
                if modes['h_flip']:
                    processed_frame = cv2.flip(processed_frame, 1)
                if modes['color'] and color_lut is not None:
                    gray = cv2.cvtColor(processed_frame, cv2.COLOR_BGR2GRAY)
                    processed_frame = color_lut[gray]
                
                out.write(processed_frame)
                frame_idx += 1
                
                # Call the universal TENET progress bar
                update_tenet_progress(frame_idx, total_frames, start_time, abort_state)
            
            print("\n")
            cap.release()
            out.release()
            
            # Cleanup temp reversed video if it was created
            if temp_reversed_file and os.path.exists(temp_reversed_file):
                os.remove(temp_reversed_file)
            
            total_time = time.time() - start_time
            
            if abort_state == 2:
                print("⚠️ VIDEO RENDER ABORTED BY USER.")
                print(f"💾 Partial result (silent): {silent_output}")
            else:
                print("✅ VIDEO PROCESSING COMPLETED!")
                print(f"⏱️ Video render time: {total_time:.1f} sec.")
                
                actual_final_output = process_audio_ffmpeg(input_video, silent_output, final_output, reverse_audio)
                
                print("="*60)
                print("🎉 FULL PROCESSING SUCCESSFULLY COMPLETED!")
                print(f"💾 Final file: {actual_final_output}")
                print("="*60)
            
            while True:
                next_step = input("\n🔄 What's next?\n  [1] Load a new file\n  [2] Different settings for THIS file\n  [0] Exit program\n👉 Your choice: ").strip()
                if next_step == '0':
                    print("\n👋 Exiting program. See you!")
                    sys.exit()
                elif next_step == '1':
                    break
                elif next_step == '2':
                    break
                else:
                    print("⚠️ Enter 0, 1, or 2.")
            
            if next_step == '1':
                break