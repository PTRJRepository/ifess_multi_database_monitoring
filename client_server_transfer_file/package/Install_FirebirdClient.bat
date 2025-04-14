@echo off
echo =====================================================
echo    INSTALLASI FIREBIRD QUERY CLIENT
echo =====================================================
echo.

set INSTALL_DIR=%USERPROFILE%\FirebirdQueryClient

echo Membuat direktori instalasi di %INSTALL_DIR%...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

echo Menyalin aplikasi...
copy "dist\FirebirdQueryClient.exe" "%INSTALL_DIR%\"

echo Membuat shortcut di desktop...
powershell "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USERPROFILE%\Desktop\Firebird Query Client.lnk'); $Shortcut.TargetPath = '%INSTALL_DIR%\FirebirdQueryClient.exe'; $Shortcut.Save()"

echo.
echo Instalasi selesai!
echo Anda dapat menjalankan aplikasi melalui shortcut di desktop.
echo.
pause 