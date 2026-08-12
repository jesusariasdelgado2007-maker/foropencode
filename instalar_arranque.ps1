$startup = [Environment]::GetFolderPath('Startup')
$lnk = Join-Path $startup 'CRM.lnk'
$wsh = New-Object -ComObject WScript.Shell
$sc = $wsh.CreateShortcut($lnk)
$sc.TargetPath = 'C:\CRM\iniciar_crm.bat'
$sc.WorkingDirectory = 'C:\CRM'
$sc.Description = 'CRM - Gestor de Clientes (arranque automatico)'
$sc.Save()
Write-Host "Arranque automatico instalado en: $lnk"
