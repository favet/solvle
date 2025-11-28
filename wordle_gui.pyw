import os
import sys
import customtkinter as ctk
import threading
import math
from concurrent.futures import ProcessPoolExecutor
import sys
from collections import Counter

# ==========================================
# PART 1: THE BACKEND
# ==========================================

# Add this function near the top
def get_resource_path(relative_path):
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# UPDATE your load_word_list function to use it:
def load_word_list(filename):
    path = get_resource_path(filename) # <--- Use the new function here
    try:
        with open(path, 'r') as f:
            return [w.strip().upper() for w in f if len(w.strip()) == 5]
    except FileNotFoundError:
        return []


def get_pattern(guess, target):
    """Returns a tuple (0=Black, 1=Yellow, 2=Green)"""
    pattern = [0] * 5
    guess_arr = list(guess)
    target_arr = list(target)

    # Green Pass
    for i in range(5):
        if guess_arr[i] == target_arr[i]:
            pattern[i] = 2
            guess_arr[i] = None
            target_arr[i] = None

    # Yellow Pass
    for i in range(5):
        if pattern[i] == 2: continue
        char = guess_arr[i]
        if char is not None and char in target_arr:
            pattern[i] = 1
            target_arr[target_arr.index(char)] = None
    return tuple(pattern)

def filter_candidates(words, guess, pattern_tuple):
    filtered = []
    for word in words:
        if get_pattern(guess, word) == pattern_tuple:
            filtered.append(word)
    return filtered

def calculate_entropy(guess, possible_solutions):
    pattern_counts = {}
    for sol in possible_solutions:
        pat = get_pattern(guess, sol)
        pattern_counts[pat] = pattern_counts.get(pat, 0) + 1
        
    total = len(possible_solutions)
    entropy = 0.0
    max_group_size = 0
    num_groups = len(pattern_counts) # NEW METRIC: How many unique patterns?
    
    for count in pattern_counts.values():
        if count > max_group_size:
            max_group_size = count
        p = count / total
        entropy -= p * math.log2(p)
        
    return entropy, max_group_size, num_groups

def get_top_guesses(candidates, full_word_list, fast_mode=False):
    if not candidates: return []
    # Phase 3: Immediate End Game. If 1 or 2 words left, just guess the top candidate.
    # Don't waste time calculating burners.
    if len(candidates) <= 2: return [(candidates[0], 0.0)]

    num_candidates = len(candidates)
    
    # --- PHASE DETERMINATION ---
    # "Ruthless Endgame" triggers when we can mathematically brute-force the groups.
    # We raise this to 25 to catch the "WHELK" scenario (4 words) and "DEUCE" (7 words).
    is_ruthless_endgame = num_candidates <= 25
    
    # --- SEARCH SPACE ---
    # In Ruthless Endgame, we MUST search the full list to find splitters.
    # In Mid-Game (>25), we search full list if < 1000 candidates (your i7 handles this easily).
    if is_ruthless_endgame:
        search_space = full_word_list
    elif fast_mode:
        search_space = candidates
    else:
        search_space = full_word_list if num_candidates < 2000 else candidates

    # --- EXECUTION ---
    if len(search_space) < 50:
        results = [calculate_entropy(w, candidates) for w in search_space]
    else:
        try:
            with ProcessPoolExecutor() as executor:
                results = list(executor.map(calculate_entropy, search_space, [candidates]*len(search_space)))
        except Exception:
            results = [calculate_entropy(w, candidates) for w in search_space]

    scored = []
    candidate_set = set(candidates)

    # --- SCORING LOGIC (The 3-Metric Balance) ---
    for word, (entropy, max_group, num_groups) in zip(search_space, results):
        
        # Start with Entropy (The most important baseline)
        score = entropy
        
        if is_ruthless_endgame:
            # === RUTHLESS ENDGAME SCORING ===
            # Priority 1: MINIMIZE MAX GROUP (Minimax).
            # If a word splits 4 candidates into 1-1-1-1 (Max 1), it is perfect.
            # If a word splits into 2-1-1 (Max 2), it is punished.
            # Penalty: -1.5 points for every extra item in the clump.
            score -= (max_group - 1) * 1.5
            
            # Tiebreaker: Candidate Bonus
            # If two words separate equally well, pick the possible winner.
            if word in candidate_set:
                score += 0.25
        
        else:
            # === MID-GAME SCORING (Fixes RENEW vs RIVEN) ===
            # Priority 1: Entropy (already in score).
            # Priority 2: Number of Groups (Branching Factor).
            # RIVEN (34 groups) gets a bigger bonus than RENEW (26 groups).
            # We normalize this (34/243 * 0.5 is a nice gentle nudge).
            score += (num_groups / 243.0) * 0.5
            
            # Priority 3: Max Group Penalty (Gentle).
            # We don't want massive buckets, but we don't kill a word for it.
            score -= (max_group / num_candidates) * 0.5
            
            # Tiny candidate bias to break exact ties
            if word in candidate_set:
                score += 0.05

        scored.append((word, score, entropy))

    scored.sort(key=lambda x: x[1], reverse=True)
    
    # Display Format
    final_output = []
    for word, smart_score, raw_entropy in scored[:7]:
        final_output.append((word, raw_entropy))
        
    return final_output

def get_letter_frequencies(candidates):
    """Returns string of top 5 letters in remaining words: 'E(90%) A(80%)...'"""
    if not candidates: return ""
    total = len(candidates)
    counts = Counter()
    for w in candidates:
        # Count unique letters per word (e.g., E in SPEED counts once for probability)
        counts.update(set(w)) 
    
    stats = []
    for letter, count in counts.most_common(5):
        pct = int((count / total) * 100)
        stats.append(f"{letter} {pct}%")
    return " ".join(stats)


# ==========================================
# PART 2: THE GUI
# ==========================================

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class WordleTile(ctk.CTkEntry):
    def __init__(self, master, **kwargs):
        super().__init__(master, width=55, height=55, 
                         justify="center", font=("Arial", 28, "bold"), **kwargs)
        self.state_val = 0 
        self.colors = ["#3a3a3c", "#b59f3b", "#538d4e"] 
        self.configure(fg_color=self.colors[0], border_width=0)
        self.bind("<Button-1>", self.cycle_color)
        self.bind("<Button-3>", self.reset_color)
        self.bind("<KeyRelease>", self.on_type)

    def cycle_color(self, event=None):
        if self.cget("state") == "disabled": return
        self.state_val = (self.state_val + 1) % 3
        self.update_visuals()
        self.focus_set()

    def reset_color(self, event=None):
        if self.cget("state") == "disabled": return
        self.state_val = 0
        self.update_visuals()

    def update_visuals(self):
        self.configure(fg_color=self.colors[self.state_val])

    def on_type(self, event):
        text = self.get().upper()
        if len(text) > 1:
            self.delete(0, "end")
            self.insert(0, text[-1]) 
        elif len(text) == 1:
            self.delete(0, "end")
            self.insert(0, text)

    def set_content(self, char, state=0):
        self.state_val = state
        self.delete(0, "end")
        self.insert(0, char.upper())
        self.update_visuals()
        self.configure(state="normal") 
    
    def lock(self):
        self.configure(state="disabled", text_color="white")

class WordleSolverApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Wordle Analytics Engine")
        self.geometry("900x650") # Slightly wider for the dashboard
        
        self.all_words = load_word_list("wordlist.txt")
        self.candidates = self.all_words[:]
        self.current_row_idx = 0
        
        if not self.all_words:
            print("Error: wordlist.txt not found!")
            sys.exit()

        self.grid_columnconfigure(0, weight=0) # Grid
        self.grid_columnconfigure(1, weight=1) # Dashboard
        
        self.setup_ui()
        self.prefill_row(0, "SLATE")
        self.update_letter_stats() # Initial stats

    def setup_ui(self):
        # --- LEFT: THE GRID ---
        self.grid_frame = ctk.CTkFrame(self)
        self.grid_frame.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        
        self.rows = []
        for r in range(6):
            row_tiles = []
            for c in range(5):
                tile = WordleTile(self.grid_frame)
                tile.grid(row=r, column=c, padx=5, pady=5)
                row_tiles.append(tile)
            self.rows.append(row_tiles)

        # Controls
        self.btn_solve = ctk.CTkButton(self.grid_frame, text="CALCULATE", 
                                       height=50, font=("Arial", 14, "bold"),
                                       command=self.start_solver_thread)
        self.btn_solve.grid(row=6, column=0, columnspan=5, pady=20, sticky="ew")

        # --- RIGHT: DASHBOARD ---
        self.dash_frame = ctk.CTkFrame(self)
        self.dash_frame.grid(row=0, column=1, padx=(0, 20), pady=20, sticky="nsew")
        
        # 1. Reset Button
        self.btn_reset = ctk.CTkButton(self.dash_frame, text="↺ RESET", width=80,
                                       fg_color="#cf4646", hover_color="#8a2e2e",
                                       command=self.reset_game)
        self.btn_reset.pack(anchor="ne", pady=10, padx=10)

        # 2. Status Label
        self.lbl_status = ctk.CTkLabel(self.dash_frame, text=f"{len(self.candidates)} Possible Words", 
                                       font=("Arial", 20, "bold"))
        self.lbl_status.pack(pady=5)

        # 3. Letter Probability (The Heatmap)
        self.lbl_letters = ctk.CTkLabel(self.dash_frame, text="Top Letters: ...", 
                                        text_color="gray", font=("Consolas", 14))
        self.lbl_letters.pack(pady=(0, 20))

        # 4. Selection Detail Panel (The "Why this word?" section)
        self.detail_frame = ctk.CTkFrame(self.dash_frame, fg_color="#2b2b2b")
        self.detail_frame.pack(fill="x", padx=10, pady=5)
        
        self.lbl_sel_word = ctk.CTkLabel(self.detail_frame, text="SELECT A WORD", font=("Arial", 18, "bold"))
        self.lbl_sel_word.pack(pady=(10, 0))
        
        self.lbl_sel_stats = ctk.CTkLabel(self.detail_frame, text="Click a suggestion below to see details.", 
                                          text_color="#bbbbbb")
        self.lbl_sel_stats.pack(pady=(5, 10))

        # 5. Recommendations List (Scrollable)
        ctk.CTkLabel(self.dash_frame, text="RECOMMENDED GUESSES", font=("Arial", 12, "bold")).pack(pady=(20, 5))
        
        self.scroll_frame = ctk.CTkScrollableFrame(self.dash_frame, height=250)
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Progress Bar
        self.progress = ctk.CTkProgressBar(self.dash_frame, mode="indeterminate")
        self.progress.pack(fill="x", side="bottom")
        self.progress.set(0) # Hide initially

    def prefill_row(self, row_idx, word):
        for i, char in enumerate(word):
            self.rows[row_idx][i].set_content(char, state=0)

    def update_letter_stats(self):
        stats = get_letter_frequencies(self.candidates)
        self.lbl_letters.configure(text=f"Find these: {stats}")

    def display_recommendations(self, top_guesses):
        # Clear old buttons
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        if not top_guesses:
            ctk.CTkLabel(self.scroll_frame, text="No suggestions.").pack()
            return

        for word, entropy in top_guesses:
            # Create a button for each suggestion
            btn = ctk.CTkButton(self.scroll_frame, 
                                text=f"{word}", 
                                font=("Consolas", 14, "bold"),
                                fg_color="transparent", border_width=1, border_color="gray",
                                anchor="w",
                                command=lambda w=word, e=entropy: self.show_word_details(w, e))
            btn.pack(fill="x", pady=2)

    def show_word_details(self, word, entropy):
        """Updates the Detail Panel when a word is clicked."""
        self.lbl_sel_word.configure(text=word)
        
        # Metric 1: Is it a winner?
        is_possible = word in self.candidates
        win_chance = (1 / len(self.candidates)) * 100 if is_possible else 0
        win_str = f"Possible Answer? {'YES' if is_possible else 'NO'} ({win_chance:.1f}%)"
        color = "#538d4e" if is_possible else "#cf4646"

        # Metric 2: Expected Remaining
        # Math approximation: N / 2^Entropy
        if len(self.candidates) > 1:
            expected_remaining = len(self.candidates) / (2**entropy)
            rem_str = f"Leaves approx. {max(1, int(expected_remaining))} words"
        else:
            rem_str = "Game Over"

        details = f"{win_str}\nInfo Score: {entropy:.2f} bits\n{rem_str}"
        self.lbl_sel_stats.configure(text=details, text_color=color)

    def reset_game(self):
        self.candidates = self.all_words[:]
        self.current_row_idx = 0
        for r in range(6):
            for c in range(5):
                self.rows[r][c].configure(state="normal") 
                self.rows[r][c].set_content("", state=0)
        
        self.prefill_row(0, "SLATE")
        self.lbl_status.configure(text=f"{len(self.candidates)} Possible Words")
        self.update_letter_stats()
        self.lbl_sel_word.configure(text="SELECT A WORD")
        self.lbl_sel_stats.configure(text="Click a suggestion below...", text_color="#bbbbbb")
        
        # Clear recommendations
        for widget in self.scroll_frame.winfo_children(): widget.destroy()

    def start_solver_thread(self):
            row = self.rows[self.current_row_idx]
            guess_word = "".join([t.get() for t in row]).upper()
            if len(guess_word) != 5:
                # You might want to show an error or just return
                return
            
            pattern = tuple([t.state_val for t in row])
            
            # Lock row
            for t in row: t.lock()
            
            self.btn_solve.configure(state="disabled", text="THINKING...")
            # Check if the reset button exists before trying to configure it
            if hasattr(self, 'btn_reset'):
                self.btn_reset.configure(state="disabled")
                
            self.progress.start()
            
            # --- THE FIX IS HERE ---
            # We explicitly pass 'False' as the 3rd argument (is_fast).
            # This matches the definition: def run_backend_logic(self, guess, pattern, is_fast):
            thread = threading.Thread(target=self.run_backend_logic, args=(guess_word, pattern, False))
            
            thread.daemon = True
            thread.start()

    def run_backend_logic(self, guess, pattern, is_fast):
        try:
            # A. Filter Candidates
            new_candidates = filter_candidates(self.candidates, guess, pattern)
            self.candidates = new_candidates
            
            # B. Check for Win/Loss
            if all(p == 2 for p in pattern):
                self.after(0, lambda: self.finish_game(True, guess))
                return
            if not self.candidates:
                self.after(0, lambda: self.finish_game(False, guess))
                return

            # C. Calculate Entropy
            top_guesses = get_top_guesses(self.candidates, self.all_words, fast_mode=is_fast)
            
            # D. Update UI
            self.after(0, lambda: self.update_ui_after_solve(top_guesses))
            
        except Exception as e:
            # THIS PREVENTS THE "STUCK BUTTON"
            print(f"CRASH IN THREAD: {e}") # Prints to console
            self.after(0, lambda: self.handle_crash(str(e)))

    def handle_crash(self, error_message):
        self.progress.stop()
        self.btn_solve.configure(state="normal", text="CALCULATE")
        self.btn_reset.configure(state="normal")
        self.update_log(f"ERROR OCCURRED:\n{error_message}\n\nTry Resetting.")

    def update_ui_after_solve(self, top_guesses):
            self.progress.stop()
            
            # 1. Wake up the Calculate Button
            self.btn_solve.configure(state="normal", text="CALCULATE")
            
            # 2. Wake up the Reset Button (CRITICAL FIX)
            if hasattr(self, 'btn_reset'):
                self.btn_reset.configure(state="normal")
            
            self.lbl_status.configure(text=f"{len(self.candidates)} Possible Words")
            
            self.update_letter_stats()
            self.display_recommendations(top_guesses)
            
            # Auto-select the best one
            if top_guesses:
                best_word, best_score = top_guesses[0]
                self.show_word_details(best_word, best_score)
                self.current_row_idx += 1
                if self.current_row_idx < 6:
                    self.prefill_row(self.current_row_idx, best_word)

    def finish_game(self, won, word):
            self.progress.stop()
            
            # 1. Force the Reset Button to Unlock (The Fix)
            if hasattr(self, 'btn_reset'):
                self.btn_reset.configure(state="normal")
                
            # 2. Also Unlock Calculate (just in case)
            self.btn_solve.configure(state="normal", text="CALCULATE")

            # 3. Update the UI Text
            self.lbl_status.configure(text="SOLVED!" if won else "GAME OVER")
            
            # Safe update for the detail labels
            if hasattr(self, 'lbl_sel_word'):
                self.lbl_sel_word.configure(text=word if won else "ERROR")
            
            if hasattr(self, 'lbl_sel_stats'):
                msg = "Congratulations!" if won else "No words match inputs."
                self.lbl_sel_stats.configure(text=msg, text_color="white")
                
            # Log the result
            log_msg = f"SOLVED!\n\nWord: {word}" if won else "No candidates left."
            self.update_log(log_msg)

if __name__ == "__main__":
    # REQUIRED for Windows EXEs using multiprocessing
    from multiprocessing import freeze_support
    freeze_support() 
    
    app = WordleSolverApp()
    app.mainloop()
