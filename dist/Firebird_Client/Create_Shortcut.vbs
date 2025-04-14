Set WshShell = CreateObject("WScript.Shell")
strDesktop = WshShell.SpecialFolders("Desktop")
Set oShellLink = WshShell.CreateShortcut(strDesktop & "\Firebird Client.lnk")
oShellLink.TargetPath = WshShell.CurrentDirectory & "\Firebird_Client.exe"
oShellLink.WorkingDirectory = WshShell.CurrentDirectory
oShellLink.Description = "Firebird Client Application"
oShellLink.Save

MsgBox "Shortcut created on desktop!", vbInformation, "Shortcut Created"
