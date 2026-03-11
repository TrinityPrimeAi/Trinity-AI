
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import time

from hardware_info import get_hardware_summary, summary_to_text, dump_full_wmi_raw, save_summary_txt


def show_hardware_window(parent):
   
    window = tk.Toplevel(parent)
    window.title("Hardware - Resumo")
    window.geometry("800x600")

    # Top: resumo (scrolledtext)
    txt = scrolledtext.ScrolledText(window, wrap=tk.WORD, font=("Consolas", 10))
    txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    # Bottom bar com botões fixos
    bottom = ttk.Frame(window)
    bottom.pack(fill=tk.X, side=tk.BOTTOM, padx=8, pady=6)

    status_lbl = ttk.Label(bottom, text="Pronto.")
    status_lbl.pack(side=tk.LEFT, padx=6)

    def disable_buttons():
        btn_save.config(state="disabled")
        btn_full.config(state="disabled")
        btn_close.config(state="disabled")

    def enable_buttons():
        btn_save.config(state="normal")
        btn_full.config(state="normal")
        btn_close.config(state="normal")

    def refresh_summary():
        status_lbl.config(text="Coletando resumo...")
        window.update_idletasks()
        try:
            summary = get_hardware_summary()
            text = summary_to_text(summary)
            txt.configure(state="normal")
            txt.delete("1.0", tk.END)
            txt.insert(tk.END, text)
            txt.configure(state="disabled")
            status_lbl.config(text=f"Resumo atualizado ({time.strftime('%H:%M:%S')}).")
        except Exception as e:
            status_lbl.config(text=f"Erro ao gerar resumo: {e}")

    def save_summary():
        path = filedialog.asksaveasfilename(parent=window, defaultextension=".txt",
                                            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                                            title="Salvar resumo como...")
        if not path:
            return
        try:
            save_summary_txt(path)
            messagebox.showinfo("Salvo", f"Resumo salvo em:\n{path}")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao salvar resumo: {e}")

    def generate_full_dump():
        if os.name != "nt":
            messagebox.showwarning("Não suportado", "Dump FULL WMI só é suportado em Windows.")
            return

        path = filedialog.asksaveasfilename(parent=window, defaultextension=".txt",
                                            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                                            title="Salvar FULL WMI como...")
        if not path:
            return

        
        def worker():
            try:
                disable_buttons()
                status_lbl.config(text="Gerando FULL WMI (pode demorar e gerar arquivo grande)...")
                window.update_idletasks()
                dump_full_wmi_raw(path, timeout=600)  # 10 minutos default - pode ajustar
                status_lbl.config(text=f"FULL WMI salvo em {path}")
                messagebox.showinfo("Concluído", f"FULL WMI salvo em:\n{path}")
            except Exception as e:
                status_lbl.config(text=f"Erro no dump: {e}")
                messagebox.showerror("Erro", f"Falha ao gerar FULL WMI:\n{e}")
            finally:
                enable_buttons()

        threading.Thread(target=worker, daemon=True).start()

    btn_save = ttk.Button(bottom, text="Salvar resumo (TXT)", command=save_summary)
    btn_save.pack(side=tk.RIGHT, padx=6)

    btn_full = ttk.Button(bottom, text="Gerar FULL WMI (AVANÇADO)", command=generate_full_dump)
    btn_full.pack(side=tk.RIGHT, padx=6)

    btn_refresh = ttk.Button(bottom, text="Atualizar resumo", command=refresh_summary)
    btn_refresh.pack(side=tk.RIGHT, padx=6)

    btn_close = ttk.Button(bottom, text="Fechar", command=window.destroy)
    btn_close.pack(side=tk.RIGHT, padx=6)

    refresh_summary()

    window.transient(parent)
    window.grab_set()
    parent.wait_window(window)
