"""
PyInstaller hook for customtkinter
Ensures theme assets and icons are included in the build
"""
from PyInstaller.utils.hooks import collect_data_files
import customtkinter

# Collect all data files from customtkinter (themes, icons, etc.)
datas = collect_data_files('customtkinter')
