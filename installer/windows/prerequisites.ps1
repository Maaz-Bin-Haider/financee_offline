# Read-only diagnostics. No settings, services, distros or registry keys changed.
$ErrorActionPreference = 'Stop'
$os = Get-CimInstance Win32_OperatingSystem
$computer = Get-CimInstance Win32_ComputerSystem
$cpu = @(Get-CimInstance Win32_Processor)[0]
$arch = $env:PROCESSOR_ARCHITEW6432
if (-not $arch) { $arch = $env:PROCESSOR_ARCHITECTURE }
$features = @{}
Get-CimInstance Win32_OptionalFeature | Where-Object { $_.Name -in @('VirtualMachinePlatform','Microsoft-Windows-Subsystem-Linux') } | ForEach-Object { $features[$_.Name] = [int]$_.InstallState }
$wslVersion = $null
$wslExe = Join-Path $env:WINDIR 'System32\wsl.exe'
if (Test-Path $wslExe) {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = (& $wslExe --version 2>&1 | Out-String) -replace "`0", ''
        $wslExitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreference }
    if ($wslExitCode -eq 0 -and $output -match '(\d+\.\d+\.\d+)') { $wslVersion = $Matches[1] }
}
@{
    system = 'Windows'; architecture = $arch; build = [int]$os.BuildNumber
    edition = $os.Caption; product_type = [int]$os.ProductType
    ram_bytes = [long]$computer.TotalPhysicalMemory
    virtualization = [bool]($computer.HypervisorPresent -or $cpu.VirtualizationFirmwareEnabled)
    slat = [bool]($computer.HypervisorPresent -or $cpu.SecondLevelAddressTranslationExtensions)
    wsl_version = $wslVersion; features = $features
    boot_id = $os.LastBootUpTime.ToUniversalTime().ToString('o')
    reboot_pending = [bool]((Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending') -or (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired'))
} | ConvertTo-Json -Depth 4 -Compress
