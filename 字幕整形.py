import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from tkinter import scrolledtext
import json

def split_text(text):
    raw_lines = text.splitlines()
    processed_lines = []
    
    for raw_line in raw_lines:
        line = raw_line.strip(' 　\t')
        if not line:
            continue
            
        parts = split_single_line(line)
        
        # セリフ行（「で始まる行）なら、分割数分だけ元のセリフ全体を繰り返す
        if line.startswith('「'):
            for _ in range(len(parts)):
                processed_lines.append(line)
        else:
            # 地の文なら分割結果をそのまま追加
            for part in parts:
                processed_lines.append(part)
                
    return processed_lines

def split_single_line(line):
    in_double = False  # 『』
    in_single = False  # 「」
    
    current_sentence = []
    sentences_in_line = []
    
    i = 0
    n = len(line)
    while i < n:
        char = line[i]
        
        if char == '『':
            in_double = True
            current_sentence.append(char)
        elif char == '』':
            in_double = False
            current_sentence.append(char)
        elif char == '「':
            in_single = True
            current_sentence.append(char)
        elif char == '」':
            in_single = False
            current_sentence.append(char)
        elif char == '。':
            current_sentence.append(char)
            if in_double:
                pass
            elif in_single:
                next_is_close = (i + 1 < n and line[i+1] == '」')
                if next_is_close:
                    pass
                else:
                    current_sentence.append('」')
                    sentences_in_line.append(''.join(current_sentence))
                    current_sentence = ['「']
            else:
                sentences_in_line.append(''.join(current_sentence))
                current_sentence = []
        else:
            current_sentence.append(char)
        i += 1
        
    if current_sentence:
        s = ''.join(current_sentence).strip(' 　\t')
        if s:
            if s.startswith('「') and not s.endswith('」'):
                s += '」'
            elif not s.startswith('「') and s.endswith('」'):
                s = '「' + s
            sentences_in_line.append(s)
            
    result = []
    for s in sentences_in_line:
        s_clean = s.strip(' 　\t')
        if s_clean:
            result.append(s_clean)
            
    return result

class SubtitleApp:
    def __init__(self, root):
        self.root = root
        self.root.title("字幕整形ツール")
        self.root.geometry("800x700")
        self.root.configure(bg="#1e1e1e")
        
        # UIテーマ設定
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure(".", background="#1e1e1e", foreground="#ffffff")
        self.style.configure("TLabel", font=("Yu Gothic", 10), background="#1e1e1e", foreground="#ffffff")
        self.style.configure("TButton", font=("Yu Gothic", 10, "bold"), background="#007acc", foreground="#ffffff", borderwidth=0)
        self.style.map("TButton", background=[("active", "#005999")])
        self.style.configure("TCheckbutton", font=("Yu Gothic", 10), background="#1e1e1e", foreground="#ffffff")
        self.style.map("TCheckbutton", background=[("active", "#1e1e1e")])
        
        # 開始番号の排他選択用変数
        self.start_003_var = tk.BooleanVar(value=False)
        self.start_004_var = tk.BooleanVar(value=True) # デフォルト004
        
        self.create_widgets()
        
    def create_widgets(self):
        # 1. 開始番号選択エリア
        header_frame = tk.Frame(self.root, bg="#1e1e1e", pady=10)
        header_frame.pack(fill=tk.X, padx=15)
        
        lbl_start = ttk.Label(header_frame, text="開始番号:")
        lbl_start.pack(side=tk.LEFT, padx=(0, 10))
        
        self.chk_003 = ttk.Checkbutton(header_frame, text="003から開始", variable=self.start_003_var, command=self.on_chk_003)
        self.chk_003.pack(side=tk.LEFT, padx=10)
        
        self.chk_004 = ttk.Checkbutton(header_frame, text="004から開始", variable=self.start_004_var, command=self.on_chk_004)
        self.chk_004.pack(side=tk.LEFT, padx=10)
        
        # 2. テキスト入力エリア
        input_label = ttk.Label(self.root, text="入力テキスト（ペーストしてください）:")
        input_label.pack(anchor=tk.W, padx=15, pady=(10, 5))
        
        self.input_text = scrolledtext.ScrolledText(self.root, height=12, bg="#2d2d2d", fg="#ffffff", insertbackground="#ffffff", font=("Yu Gothic", 11), bd=0, padx=5, pady=5)
        self.input_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        # 3. アクションボタンエリア
        btn_frame = tk.Frame(self.root, bg="#1e1e1e", pady=10)
        btn_frame.pack(fill=tk.X, padx=15)
        
        self.btn_run = ttk.Button(btn_frame, text="整形実行", command=self.run_formatting, width=15)
        self.btn_run.pack(side=tk.LEFT, padx=(0, 10))
        
        self.btn_clear = ttk.Button(btn_frame, text="クリア", command=self.clear_all, width=10)
        self.btn_clear.pack(side=tk.LEFT)
        
        # 4. 整形結果出力エリア
        output_label = ttk.Label(self.root, text="整形後のJSON結果:")
        output_label.pack(anchor=tk.W, padx=15, pady=(10, 5))
        
        self.output_text = scrolledtext.ScrolledText(self.root, height=12, bg="#2d2d2d", fg="#a9ff94", insertbackground="#ffffff", font=("Yu Gothic", 11), bd=0, padx=5, pady=5)
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        self.output_text.config(state=tk.DISABLED) # 最初は編集不可に
        
        # 5. コピーボタンエリア
        copy_frame = tk.Frame(self.root, bg="#1e1e1e", pady=10)
        copy_frame.pack(fill=tk.X, padx=15)
        
        self.btn_copy = ttk.Button(copy_frame, text="結果をクリップボードにコピー", command=self.copy_to_clipboard, width=30)
        self.btn_copy.pack(side=tk.RIGHT)
        
    def on_chk_003(self):
        if self.start_003_var.get():
            self.start_004_var.set(False)
        else:
            self.start_004_var.set(True)
            
    def on_chk_004(self):
        if self.start_004_var.get():
            self.start_003_var.set(False)
        else:
            self.start_003_var.set(True)
            
    def run_formatting(self):
        text = self.input_text.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("警告", "入力テキストが空です。")
            return
            
        lines = split_text(text)
        if not lines:
            messagebox.showwarning("警告", "有効な文章が抽出されませんでした。")
            return
            
        start_num = 3 if self.start_003_var.get() else 4
        
        result_dict = {}
        for i, line in enumerate(lines):
            key = f"{start_num + i:03d}"
            result_dict[key] = line
            
        json_str = json.dumps(result_dict, ensure_ascii=False, indent=2)
        
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", json_str)
        self.output_text.config(state=tk.DISABLED)
        
    def copy_to_clipboard(self):
        res = self.output_text.get("1.0", tk.END).strip()
        if not res:
            messagebox.showwarning("警告", "コピーする結果がありません。")
            return
            
        self.root.clipboard_clear()
        self.root.clipboard_append(res)
        self.root.update()
        messagebox.showinfo("成功", "JSONをクリップボードにコピーしました。")
        
    def clear_all(self):
        self.input_text.delete("1.0", tk.END)
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)
        self.output_text.config(state=tk.DISABLED)

if __name__ == "__main__":
    root = tk.Tk()
    app = SubtitleApp(root)
    root.mainloop()
