$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\CRM.lnk')
$shortcut.TargetPath = 'C:\CRM\iniciar_crm.bat'
$shortcut.WorkingDirectory = 'C:\CRM'
$shortcut.Description = 'Abrir CRM - Gestor de Clientes'
$shortcut.IconLocation = 'shell32.dll,13'
$shortcut.Save()
Write-Host 'Acceso directo creado en el Escritorio: CRM.lnk'
