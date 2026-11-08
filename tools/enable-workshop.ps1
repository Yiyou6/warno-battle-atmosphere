param([string]$GameDirectory, [string]$UserDataDirectory, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
function Get-Digest([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}
try {
    $package = Split-Path -Parent $PSScriptRoot
    $manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $gameCandidates = New-Object System.Collections.Generic.List[string]
    if ($GameDirectory) { $gameCandidates.Add($GameDirectory) }
    $ancestor = Get-Item -LiteralPath $package
    while ($ancestor) {
        if ($ancestor.Name -eq 'steamapps') { $gameCandidates.Add((Join-Path $ancestor.FullName 'common\WARNO')) }
        $ancestor = $ancestor.Parent
    }
    if (-not $GameDirectory) {
        $steam = (Get-ItemProperty -Path 'HKCU:\Software\Valve\Steam' -ErrorAction SilentlyContinue).SteamPath
        if ($steam) {
            $gameCandidates.Add((Join-Path $steam 'steamapps\common\WARNO'))
            $libraries = Join-Path $steam 'steamapps\libraryfolders.vdf'
            if (Test-Path -LiteralPath $libraries) {
                $vdf = Get-Content -LiteralPath $libraries -Raw
                foreach ($match in [regex]::Matches($vdf, '"path"\s+"([^"]+)"')) {
                    $gameCandidates.Add((Join-Path $match.Groups[1].Value.Replace('\\','\') 'steamapps\common\WARNO'))
                }
            }
        }
    }
    $game = $gameCandidates | Where-Object { Test-Path -LiteralPath (Join-Path $_ 'WARNO.exe') } | Select-Object -First 1
    if (-not $game) { throw '没有找到游戏安装目录。请将此文件夹放到游戏所在盘后重试。' }
    $game = (Resolve-Path -LiteralPath $game).Path
    if ((Get-Digest (Join-Path $game 'WARNO.exe')) -ne $manifest.game_sha256) {
        throw '当前游戏版本不匹配，请等待本模组更新后再启用。'
    }
    foreach ($entry in $manifest.files.PSObject.Properties) {
        if ($entry.Name -notmatch '^(Config\.ini|Gen/[^:]+|完整启用/version\.dll)$' -or $entry.Name -match '(^|/)\.\.(/|$)') { throw '文件清单不正确。' }
        $file = Join-Path $package $entry.Name
        if ((Get-Digest $file) -ne $entry.Value) { throw ('订阅文件不完整，请重新下载：' + $entry.Name) }
    }
    $loader = Join-Path $game 'version.dll'
    if ((Test-Path -LiteralPath $loader) -and (Get-Digest $loader) -ne $manifest.files.'完整启用/version.dll') {
        throw '游戏目录已有其他工具的同名文件，已停止启用，未覆盖。'
    }
    if (-not $UserDataDirectory) {
        $saved = (Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders' -ErrorAction SilentlyContinue).'{4C5C32FF-BB9D-43B0-B4B0-2D72E5E0AAA4}'
        if (-not $saved) { $saved = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'Saved Games' }
        $UserDataDirectory = Join-Path ([Environment]::ExpandEnvironmentVariables($saved)) 'EugenSystems\WARNO'
    }
    $userData = [IO.Path]::GetFullPath($UserDataDirectory)
    $targetMod = Join-Path $userData 'mod\BattleAtmosphere'
    $targetRuntime = Join-Path $game 'Mods\BattleAtmosphere\Runtime\runtime.ini'
    $activation = Join-Path $userData 'mod\Config.ini'
    # The installed companion is a local unpublished copy (native ID 0),
    # distinct from the downloadable workshop carrier. Native lookup includes
    # inactive local mods, so reject another local ID 0 before changing files.
    $modDirectory = Join-Path $userData 'mod'
    if (Test-Path -LiteralPath $modDirectory) {
        foreach ($folder in Get-ChildItem -LiteralPath $modDirectory -Directory) {
            if ($folder.Name -eq 'BattleAtmosphere') { continue }
            $otherConfig = Join-Path $folder.FullName 'Config.ini'
            if (Test-Path -LiteralPath $otherConfig) {
                $other = [IO.File]::ReadAllText($otherConfig, [Text.Encoding]::UTF8)
                if ($other -match '(?m)^ID\s*=\s*0\s*(;[^\r\n]*)?$') {
                    throw '发现另一个未发布的本地模组，请先将它移出模组文件夹再启用。'
                }
            }
        }
    }
    if ($CheckOnly) { Write-Output '文件及游戏版本检查通过，未修改任何安装文件。'; exit 0 }
    if (Get-Process WARNO -ErrorAction SilentlyContinue) { throw '请先正常退出游戏，再重新运行此文件。' }
    $backup = Join-Path $userData ('打电脑优化备份\' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    function Save-Existing([string]$Source,[string]$Relative) {
        if (Test-Path -LiteralPath $Source -PathType Leaf) {
            $destination = Join-Path $backup $Relative
            New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
            Copy-Item -LiteralPath $Source -Destination $destination
        }
    }
    Save-Existing $loader 'game\version.dll'
    Save-Existing $targetRuntime 'game\runtime.ini'
    Save-Existing $activation 'activation.ini'
    foreach ($entry in $manifest.files.PSObject.Properties) {
        if ($entry.Name -eq '完整启用/version.dll') { continue }
        $destination = Join-Path $targetMod $entry.Name
        Save-Existing $destination ('mod\' + $entry.Name)
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $package $entry.Name) -Destination $destination -Force
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $targetRuntime) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'version.dll') -Destination $loader -Force
    [IO.File]::WriteAllText($targetRuntime, "[Runtime]`r`nEnabled=1`r`n", [Text.Encoding]::ASCII)
    # Select the local companion so the unchanged runtime's exact activation gate works.
    [IO.File]::WriteAllText($activation, "[Config]`r`nActivatedMods = BattleAtmosphere|`r`n", [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $backup '说明.txt'), "这是启用前的备份。启用时已暂时关闭其他模组，游戏原始文件未被替换。", [Text.UTF8Encoding]::new($true))
    foreach ($entry in $manifest.files.PSObject.Properties) {
        $destination = if ($entry.Name -eq '完整启用/version.dll') { $loader } else { Join-Path $targetMod $entry.Name }
        if ((Get-Digest $destination) -ne $entry.Value) { throw '复制后检查失败，请重新启用。' }
    }
    $localConfig = Join-Path $targetMod 'Config.ini'
    $localText = [IO.File]::ReadAllText($localConfig, [Text.Encoding]::UTF8)
    $localText = [regex]::Replace($localText, '(?m)^Name\s*=.*$', 'Name = BattleAtmosphere')
    $localText = [regex]::Replace($localText, '(?m)^ID\s*=.*$', 'ID = 0')
    [IO.File]::WriteAllText($localConfig, $localText, [Text.UTF8Encoding]::new($false))
    Write-Output '启用完成。打开游戏后即可进入遭遇战。其他模组已暂时关闭，原有设置已备份。'
} catch {
    Write-Output ('启用失败：' + $_.Exception.Message)
    exit 1
}
