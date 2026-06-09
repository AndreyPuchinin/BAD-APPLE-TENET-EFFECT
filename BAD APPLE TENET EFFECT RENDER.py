import cv2
import numpy as np
import os
import sys
import time
import re
import shutil
import subprocess

# ==========================================
# УТИЛИТЫ (Вне классов)
# ==========================================

def get_key_nonblocking():
    """Checks for key press without blocking program execution."""
    if os.name == 'nt':  # Windows
        import msvcrt
        if msvcrt.kbhit():
            return msvcrt.getch().decode('utf-8', errors='ignore').lower()
        return None
    else:  # Linux / macOS
        import select, termios, tty
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

# ==========================================
# КЛАСС 1: MENU (Интерфейс и Состояние)
# ==========================================

class Menu:
    def __init__(self):
        self.current_section_link = self.section_file_select
        self.exit_program = False
        self.render_requested = False
        
        self.selected_file = None
        self.modes = {'time': False, 'h_flip': False, 'color': False}
        self.reverse_audio = False
        self.source_color_stops = None
        self.target_color_stops = None

    def validate_file(self):
        """Проверяет существование выбранного файла. Если его нет, возвращает False."""
        if not self.selected_file or not os.path.exists(self.selected_file):
            print("\n" + "="*60)
            print(" ⚠️ CRITICAL ERROR: FILE NOT FOUND ")
            print("="*60)
            print(f" The file '{self.selected_file}' was deleted, moved, or renamed!")
            print(" Returning to file selection menu...\n")
            return False
        return True

    def choose_menu_point(self):
        """Главная точка входа для ProcessManager."""
        next_section = self.current_section_link()
        if next_section is not None:
            self.current_section_link = next_section
        return next_section

    def section_file_select(self):
        """Секция выбора файла с безопасным обновлением списка (без рекурсии)."""
        while True:  # Этот цикл гарантирует отсутствие рекурсии!
            valid_extensions = ('.mp4', '.avi', '.mkv', '.mov', '.webm')
            # Переменная files ПЕРЕЗАПИСЫВАЕТСЯ каждый раз при входе в цикл или после 'continue'
            files = [f for f in os.listdir('.') if f.lower().endswith(valid_extensions)]
            
            if not files:
                print("\n" + "="*60)
                print(" ⚠️ WARNING: No video files found in the directory! ")
                print(" Please add a video file, then press Enter to refresh...")
                input("="*60)
                continue  # Перезапускаем цикл, переменные перетираются, стек не растет

            print("\n" + "="*60)
            print(" 📁 SELECT SOURCE FILE")
            print("="*60)
            for i, f in enumerate(files, 1):
                print(f"  [{i}] {f}")
            
            # Добавляем опцию Refresh
            print("  [r] 🔄 REFRESH FILE LIST (Update directory state)")
            print("  [0] 🚪 EXIT PROGRAM")
            
            choice = input("\n👉 Enter file number, 'r' to refresh, or 0 to exit: ").strip().lower()
            
            if choice == '0':
                self.exit_program = True
                return None
            
            # ВОТ ОНО: Магия без рекурсии!
            elif choice == 'r':
                # Оператор continue мгновенно перебрасывает нас в начало while True.
                # Список files будет получен заново через os.listdir.
                # Глубина стека вызовов не увеличивается ни на 1.
                continue 
            
            else:
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(files):
                        self.selected_file = files[idx]
                        # Переход к следующему состоянию меню (не рекурсия, а смена ссылки)
                        return self.section_modes 
                    print("⚠️ Error: Number out of range.")
                except ValueError:
                    print("⚠️ Error: Please enter a valid number or 'r'.")

    def section_modes(self):
        """Секция выбора режимов видео."""
        # ПРОВЕРКА БЕЗОПАСНОСТИ
        if not self.validate_file():
            return self.section_file_select

        print("\n" + "="*60)
        print(" ⚙️  SELECT VIDEO PROCESSING MODES")
        print("="*60)
        print("  [1] Reverse Time")
        print("  [2] Mirror Horizontal")
        print("  [3] Color Gradient Mapping (Source → Target)")
        print("  [0] ⬅️  GO BACK TO FILE SELECTION")
        
        while True:
            choice = input("\n👉 Enter mode numbers separated by space (or 0 to go back): ").strip()
            if choice == '0':
                return self.section_file_select
            
            try:
                modes = [int(x) for x in choice.split()]
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
        """Секция настройки аудио."""
        # ПРОВЕРКА БЕЗОПАСНОСТИ
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
        """Универсальная функция для ввода одной цветовой шкалы."""
        print("\n" + "="*60)
        print(f" 🎨 {prompt_title}")
        print("="*60)
        print(f"  Format: percent(r,g,b) separated by space.")
        print(f"  Example: {prompt_example}")
        print("  [0] or 'back' ⬅️ GO BACK")
        
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

    def section_color(self):
        """Секция ввода ДВУХ цветовых шкал (Source → Target)."""
        # ПРОВЕРКА БЕЗОПАСНОСТИ
        if not self.validate_file():
            return self.section_file_select

        # ШАГ 1: Исходная шкала
        source_stops = self._get_single_scale(
            "SOURCE COLOR SCALE (What to replace)",
            "0(255,0,0) 100(0,0,255)"
        )
        if source_stops is None:
            return self.section_audio
        
        # ШАГ 2: Целевая шкала
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
        """Вспомогательный метод для сигнализации о готовности к рендеру."""
        self.render_requested = True
        return None

    def post_render_menu(self):
        """Меню после завершения рендера."""
        print("\n" + "="*60)
        print(" 🔄 POST-RENDER ACTIONS")
        print("="*60)
        while True:
            choice = input("\n🔄 What's next?\n  [1] Load a new file\n  [2] Different settings for THIS file\n  [0] Exit program\n👉 Your choice: ").strip()
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
# КЛАСС 2: RENDER (Чистый бэкенд и Отрисовка)
# ==========================================

class Render:
    def __init__(self):
        self.abort_state = 0

    def taskbar(self, current, total, start_time, abort_state, bar_width=50):
        """Универсальная TENET-полоса загрузки."""
        if not total: return
        reverse_ratio = 1.0 - (current / total)
        percentage = int(reverse_ratio * 100)
        filled = int(reverse_ratio * bar_width)
        bar_str = '█' * filled + '░' * (bar_width - filled)
        
        elapsed = time.time() - start_time
        speed = current / elapsed if elapsed > 0.1 else 0.0
        eta = (total - current) / speed if speed > 0 else 0
        
        h, rem = divmod(int(eta), 3600)
        m, s = divmod(rem, 60)
        eta_str = f"{h}h {m:02d}m {s:02d}s" if h > 0 else f"{m:02d}m {s:02d}s"
        
        if abort_state == 0:
            line = f"\r{percentage:3d}% - [{bar_str}] | {speed:5.1f} fps | ETA: {eta_str} | [Q=abort]"
        else:
            line = f"\r{percentage:3d}% - [{bar_str}] | ⚠️ CONFIRM ABORT (y/n): "
            
        sys.stdout.write(line)
        sys.stdout.flush()

    def apply_mirror(self, frame):
        """Режим: Зеркало."""
        return cv2.flip(frame, 1)

    def apply_color_mapping(self, frame, source_stops, target_stops):
        """Режим: Цветовой градиентный маппинг с автоматическим выравниванием зон."""
        # 1. Выравниваем целевую шкалу под проценты исходной
        source_pcts = [stop[0] for stop in source_stops]
        target_pcts = [stop[0] for stop in target_stops]
        
        target_r = [stop[1] for stop in target_stops]
        target_g = [stop[2] for stop in target_stops]
        target_b = [stop[3] for stop in target_stops]
        
        aligned_r = np.interp(source_pcts, target_pcts, target_r)
        aligned_g = np.interp(source_pcts, target_pcts, target_g)
        aligned_b = np.interp(source_pcts, target_pcts, target_b)
        
        aligned_target_stops = [
            (source_pcts[i], int(aligned_r[i]), int(aligned_g[i]), int(aligned_b[i]))
            for i in range(len(source_stops))
        ]
        
        # 2. Применяем маппинг
        result = frame.copy().astype(np.float32)
        
        for i in range(len(source_stops) - 1):
            src_start = np.array([source_stops[i][1], source_stops[i][2], source_stops[i][3]], dtype=np.float32)
            src_end = np.array([source_stops[i+1][1], source_stops[i+1][2], source_stops[i+1][3]], dtype=np.float32)
            
            tgt_start = np.array([aligned_target_stops[i][1], aligned_target_stops[i][2], aligned_target_stops[i][3]], dtype=np.float32)
            tgt_end = np.array([aligned_target_stops[i+1][1], aligned_target_stops[i+1][2], aligned_target_stops[i+1][3]], dtype=np.float32)
            
            src_direction = src_end - src_start
            direction_length_sq = np.sum(src_direction * src_direction)
            
            if direction_length_sq < 1e-6:
                continue
            
            pixel_vector = frame.astype(np.float32) - src_start
            dot_product = np.sum(pixel_vector * src_direction, axis=2)
            t = np.clip(dot_product / direction_length_sq, 0, 1)
            
            interpolated_color = tgt_start + t[:, :, np.newaxis] * (tgt_end - tgt_start)
            mask = (t > 0) & (t < 1)
            result[mask] = interpolated_color[mask]
        
        return np.clip(result, 0, 255).astype(np.uint8)

    def process_audio_ffmpeg(self, input_video, silent_video, final_output, reverse_audio):
        """Обработка аудио через FFmpeg."""
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
            print("⏪ Reversing audio...")
            subprocess.run(["ffmpeg", "-y", "-i", temp_wav, "-af", "areverse", temp_rev_wav],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            audio_to_mux = temp_rev_wav

        print("🔗 Merging processed video and audio...")
        subprocess.run([
            "ffmpeg", "-y", "-i", silent_video, "-i", audio_to_mux, 
            "-c:v", "copy", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0", final_output
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if os.path.exists(silent_video): os.remove(silent_video)
        if os.path.exists(temp_wav): os.remove(temp_wav)
        if os.path.exists(temp_rev_wav): os.remove(temp_rev_wav)
        
        print("✅ Audio successfully processed and merged!")
        return final_output

    def run_pipeline(self, input_video, modes, reverse_audio, source_stops, target_stops):
        """Главный конвейер рендера."""
        # ФИНАЛЬНАЯ ПРОВЕРКА БЕЗОПАСНОСТИ ПЕРЕД ЗАПУСКОМ
        if not os.path.exists(input_video):
            print("\n" + "="*60)
            print(" ⚠️ CRITICAL ERROR: FILE DISAPPEARED DURING SETUP ")
            print("="*60)
            print(f" The file '{input_video}' is no longer accessible.")
            print(" Aborting render and returning to file selection.\n")
            return "FILE_MISSING"

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
        
        if modes['time']:
            print("\n⏪ Reversing video timeline via FFmpeg (Memory-Safe Mode)...")
            temp_reversed_file = "temp_reversed_source.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-i", input_video, "-vf", "reverse", "-an", 
                "-c:v", "libx264", "-preset", "ultrafast", temp_reversed_file
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if os.path.exists(temp_reversed_file):
                working_video = temp_reversed_file
                print("✅ Video reversed on disk successfully. Zero RAM used.")

        cap = cv2.VideoCapture(working_video)
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0: total_frames = None
            
        out = cv2.VideoWriter(silent_output, cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))
        
        print(f"\n⏳ Initializing streaming render: {width}x{height}, {fps} FPS")
        print(f"🎯 Active modes: {', '.join(suffixes) if suffixes else 'None'}")
        print("💡 Tip: Press 'Q' at any time to request abort.\n🚀 Starting pipeline:")
        
        start_time = time.time()
        frame_idx = 0
        self.abort_state = 0
        
        while True:
            ret, frame = cap.read()
            if not ret: break
            
            key = get_key_nonblocking()
            if key == 'q' and self.abort_state == 0: self.abort_state = 1
            if self.abort_state == 1:
                if key == 'y':
                    self.abort_state = 2
                    break
                elif key == 'n': self.abort_state = 0
            if self.abort_state == 2: break
            
            processed_frame = frame.copy()
            
            if modes['h_flip']:
                processed_frame = self.apply_mirror(processed_frame)
            if modes['color'] and source_stops and target_stops:
                processed_frame = self.apply_color_mapping(processed_frame, source_stops, target_stops)
            
            out.write(processed_frame)
            frame_idx += 1
            
            self.taskbar(frame_idx, total_frames, start_time, self.abort_state)
        
        print("\n")
        cap.release()
        out.release()
        if temp_reversed_file and os.path.exists(temp_reversed_file): os.remove(temp_reversed_file)
        
        if self.abort_state == 2:
            print("⚠️ VIDEO RENDER ABORTED BY USER.")
        else:
            print("✅ VIDEO PROCESSING COMPLETED!")
            self.process_audio_ffmpeg(input_video, silent_output, final_output, reverse_audio)
            print("="*60)
            print(f"🎉 FULL PROCESSING SUCCESSFULLY COMPLETED! Final file: {final_output}")
            print("="*60)
            
        return "SUCCESS"


# ==========================================
# КЛАСС 3: PROCESS MANAGER (Дирижер)
# ==========================================

class ProcessManager:
    def __init__(self):
        print("="*60)
        print(" 🌀 UNIVERSAL TENET VIDEO CONSTRUCTOR (v8.0 Bulletproof) 🌀 ")
        print("="*60)
        
        self.menu = Menu()
        self.render = Render()
        
        while True:
            while not self.menu.render_requested and not self.menu.exit_program:
                self.menu.choose_menu_point()
                
            if self.menu.exit_program:
                print("\n👋 Exiting program. See you!")
                break
                
            if self.menu.render_requested:
                result = self.render.run_pipeline(
                    self.menu.selected_file,
                    self.menu.modes,
                    self.menu.reverse_audio,
                    self.menu.source_color_stops,
                    self.menu.target_color_stops
                )
                
                # Обработка случая, когда файл исчез прямо перед рендером
                if result == "FILE_MISSING":
                    self.menu.current_section_link = self.menu.section_file_select
                    self.menu.render_requested = False
                    continue
                
                self.menu.render_requested = False
                self.menu.post_render_menu()

# ==========================================
# ТОЧКА ВХОДА
# ==========================================
if __name__ == "__main__":
    ProcessManager()