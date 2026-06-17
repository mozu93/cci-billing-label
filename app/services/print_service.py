# app/services/print_service.py
import os
import sys
import subprocess


def open_pdf(pdf_path: str) -> bool:
    """PDFをデフォルトビューアで開く"""
    if not pdf_path or not os.path.exists(pdf_path):
        return False
    try:
        if sys.platform == "win32":
            os.startfile(pdf_path)
        else:
            subprocess.Popen(["xdg-open", pdf_path])
        return True
    except Exception:
        return False


def print_pdf(pdf_path: str) -> bool:
    """OSの標準印刷機能でPDFを印刷する"""
    if not pdf_path or not os.path.exists(pdf_path):
        return False
    try:
        if sys.platform == "win32":
            subprocess.Popen(
                ["rundll32.exe",
                 "C:\\Windows\\System32\\shell32.dll,ShellExec_RunDLL",
                 "print", pdf_path],
                shell=False
            )
        else:
            subprocess.Popen(["lp", pdf_path])
        return True
    except Exception:
        return False
