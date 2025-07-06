import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import queue
import pyaudio
import wave
import os
import whisper
from datetime import datetime


class DictationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Pappa Praat")
        self.root.geometry("800x600")
        
        # Audio settings
        self.audio_format = pyaudio.paInt16
        self.channels = 1
        self.rate = 16000
        self.chunk = 1024
        self.audio = pyaudio.PyAudio()

        # Recording state
        self.recordings_dir = 'recordings'
        self.recording = False
        self.frames = []
        self.stream = None

        # Whisper model (start with base, can be changed)
        self.model = None
        self.model_size = "base"
        self.language = 'af'

        # Queue for threading
        self.transcription_queue = queue.Queue()
        
        self.setup_ui()
        self.load_whisper_model()

        # Check for transcription results periodically
        self.root.after(100, self.check_transcription_queue)

    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)

        # Title
        title_label = ttk.Label(main_frame, text="Pappa Praat", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 10))

        # Controls frame
        controls_frame = ttk.Frame(main_frame)
        controls_frame.grid(row=1, column=0, columnspan=3, pady=(0, 10), sticky=(tk.W, tk.E))

        # Record button
        self.record_btn = ttk.Button(controls_frame, text="🎤 Start Recording", 
                                    command=self.toggle_recording)
        self.record_btn.grid(row=0, column=0, padx=(0, 10))
        
        # Status label
        self.status_label = ttk.Label(controls_frame, text="Ready to record")
        self.status_label.grid(row=0, column=1, padx=(0, 10))

        # Model selection
        ttk.Label(controls_frame, text="Model:").grid(row=0, column=2, padx=(20, 5))
        self.model_var = tk.StringVar(value="base")
        model_combo = ttk.Combobox(controls_frame, textvariable=self.model_var, 
                                  values=["tiny", "base", "small", "medium", "large"],
                                  state="readonly", width=10)
        model_combo.grid(row=0, column=3, padx=(0, 10))
        model_combo.bind('<<ComboboxSelected>>', self.on_model_change)

        # Language selection
        ttk.Label(controls_frame, text="Language:").grid(row=0, column=4, padx=(20, 5))
        self.language_var = tk.StringVar(value=self.language)
        model_combo = ttk.Combobox(controls_frame, textvariable=self.language_var, 
                                  values=["af", "en"],
                                  state="readonly", width=10)
        model_combo.grid(row=0, column=5, padx=(0, 10))
        model_combo.bind('<<ComboboxSelected>>', self.on_language_change)
        
        # Text area with scrollbar
        text_frame = ttk.Frame(main_frame)
        text_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        
        self.text_area = tk.Text(text_frame, wrap=tk.WORD, font=("Arial", 12))
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text_area.yview)
        self.text_area.configure(yscrollcommand=scrollbar.set)
        
        self.text_area.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Bottom buttons
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.grid(row=3, column=0, columnspan=3, pady=(10, 0))
        
        ttk.Button(buttons_frame, text="Clear Text", 
                  command=self.clear_text).grid(row=0, column=0, padx=(0, 10))
        ttk.Button(buttons_frame, text="Save Text", 
                  command=self.save_text).grid(row=0, column=1, padx=(0, 10))
        ttk.Button(buttons_frame, text="Copy All", 
                  command=self.copy_all).grid(row=0, column=2)

    def load_whisper_model(self):
        """Load the Whisper model in a separate thread"""
        def load_model():
            try:
                self.status_label.config(text=f"Loading {self.model_size} model...")
                self.model = whisper.load_model(self.model_size)
                self.status_label.config(text="Model loaded - Ready to record")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load model: {str(e)}")
                self.status_label.config(text="Model loading failed")
        
        threading.Thread(target=load_model, daemon=True).start()

    def on_model_change(self, event=None):
        """Handle model selection change"""
        new_model = self.model_var.get()
        if new_model != self.model_size:
            self.model_size = new_model
            self.model = None
            self.load_whisper_model()

    def on_language_change(self, event=None):
        """Handle language selection change"""
        self.language = self.language_var.get()

    def toggle_recording(self):
        """Start or stop recording"""
        if not self.recording:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        """Start audio recording"""
        if self.model is None:
            messagebox.showwarning("Warning", "Please wait for the model to load first.")
            return
        
        try:
            self.frames = []
            self.stream = self.audio.open(format=self.audio_format,
                                        channels=self.channels,
                                        rate=self.rate,
                                        input=True,
                                        frames_per_buffer=self.chunk)
            
            self.recording = True
            self.record_btn.config(text="⏹️ Stop Recording")
            self.status_label.config(text="Recording... Click stop when finished")
            
            # Start recording in a separate thread
            threading.Thread(target=self.record_audio, daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start recording: {str(e)}")

    def record_audio(self):
        """Record audio data"""
        while self.recording:
            try:
                data = self.stream.read(self.chunk)
                self.frames.append(data)
            except Exception as e:
                print(f"Recording error: {e}")
                break

    def stop_recording(self):
        """Stop recording and process audio"""
        self.recording = False
        self.record_btn.config(text="🎤 Start Recording")
        self.status_label.config(text="Processing audio...")
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        
        # Process the recorded audio
        threading.Thread(target=self.process_audio, daemon=True).start()

    def process_audio(self):
        """Process recorded audio with Whisper"""
        try:
            os.makedirs(self.recordings_dir, exist_ok=True)
            temp_filename = os.path.join(self.recordings_dir, f'{int(datetime.now().timestamp())}.wav')
            # Write WAV file
            with wave.open(temp_filename, 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(self.audio.get_sample_size(self.audio_format))
                wf.setframerate(self.rate)
                wf.writeframes(b''.join(self.frames))
            
            # Transcribe with Whisper
            result = self.model.transcribe(temp_filename, language=self.language)
            transcription = result["text"].strip()
            
            # Add to queue for main thread
            self.transcription_queue.put(transcription)
            
        except Exception as e:
            print(e)
            self.transcription_queue.put(f"Error: {str(e)}")

    def check_transcription_queue(self):
        """Check for transcription results"""
        try:
            while True:
                transcription = self.transcription_queue.get_nowait()
                if transcription.startswith("Error:"):
                    messagebox.showerror("Transcription Error", transcription)
                    self.status_label.config(text="Transcription failed")
                else:
                    # Add transcription to text area
                    current_text = self.text_area.get("1.0", tk.END).strip()
                    if current_text:
                        self.text_area.insert(tk.END, "\n\n" + transcription)
                    else:
                        self.text_area.insert(tk.END, transcription)
                    
                    # Scroll to bottom
                    self.text_area.see(tk.END)
                    self.status_label.config(text="Transcription complete - Ready for next recording")
                
        except queue.Empty:
            pass
        
        # Schedule next check
        self.root.after(100, self.check_transcription_queue)

    def clear_text(self):
        """Clear the text area"""
        self.text_area.delete("1.0", tk.END)

    def save_text(self):
        """Save text to file"""
        text = self.text_area.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Warning", "No text to save.")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"dictation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(text)
                messagebox.showinfo("Success", f"Text saved to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file: {str(e)}")

    def copy_all(self):
        """Copy all text to clipboard"""
        text = self.text_area.get("1.0", tk.END).strip()
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            messagebox.showinfo("Success", "Text copied to clipboard!")
        else:
            messagebox.showwarning("Warning", "No text to copy.")
    
    def __del__(self):
        """Cleanup"""
        if hasattr(self, 'audio'):
            self.audio.terminate()

if __name__ == "__main__":
    root = tk.Tk()
    app = DictationApp(root)
    root.mainloop()
