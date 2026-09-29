<#
    Build script for the API Load Tester.

    Produces two standalone Windows executables in .\dist:
      - LoadTesterGUI.exe  (double-click desktop app, no console window)
      - load_test.exe      (command-line / interactive tool)

    Usage:
        pip install -r requirements.txt
        ./build.ps1
#>

$ErrorActionPreference = "Stop"

Write-Host "Building GUI executable (LoadTesterGUI.exe)..." -ForegroundColor Cyan
python -m PyInstaller --onefile --windowed --name LoadTesterGUI load_test_gui.py --noconfirm

Write-Host "Building CLI executable (load_test.exe)..." -ForegroundColor Cyan
python -m PyInstaller --onefile --console --name load_test load_test.py --noconfirm

Write-Host ""
Write-Host "Done. Executables are in the .\dist folder:" -ForegroundColor Green
Get-ChildItem .\dist\*.exe | Select-Object Name, Length
