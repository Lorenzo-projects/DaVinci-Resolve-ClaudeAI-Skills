[CmdletBinding()]
param(
    [string[]]$Skill,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '..\dist\skills')
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)

$availableSkills = @(
    Get-ChildItem -LiteralPath $repositoryRoot -Directory |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'SKILL.md') }
)

if ($Skill -and $Skill.Count -gt 0) {
    $selectedSkills = foreach ($skillName in $Skill) {
        $match = $availableSkills | Where-Object Name -EQ $skillName | Select-Object -First 1
        if (-not $match) {
            $availableNames = ($availableSkills.Name -join ', ')
            throw "Unknown skill '$skillName'. Available skills: $availableNames"
        }
        $match
    }
}
else {
    $selectedSkills = $availableSkills
}

$selectedSkills = @($selectedSkills | Sort-Object -Property Name -Unique)
if ($selectedSkills.Count -eq 0) {
    throw "No skill folders containing SKILL.md were found in '$repositoryRoot'."
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null

foreach ($selectedSkill in $selectedSkills) {
    $skillFile = Join-Path $selectedSkill.FullName 'SKILL.md'
    $skillText = Get-Content -LiteralPath $skillFile -Raw
    $frontMatterMatch = [regex]::Match(
        $skillText,
        '\A---\r?\n(?<frontmatter>.*?)\r?\n---(?:\r?\n|$)',
        [System.Text.RegularExpressions.RegexOptions]::Singleline
    )

    if (-not $frontMatterMatch.Success) {
        throw "Invalid SKILL.md frontmatter in '$skillFile': expected a YAML frontmatter block."
    }

    $frontMatter = $frontMatterMatch.Groups['frontmatter'].Value
    $nameMatch = [regex]::Match($frontMatter, '(?m)^name:\s*([^\r\n]+)\s*$')
    $descriptionMatch = [regex]::Match($frontMatter, '(?m)^description:\s*([^\r\n]+)\s*$')

    if (-not $nameMatch.Success -or -not $descriptionMatch.Success) {
        throw "Invalid SKILL.md frontmatter in '$skillFile': expected name and description."
    }
    if ($nameMatch.Groups[1].Value.Trim() -ne $selectedSkill.Name) {
        throw "Skill name in '$skillFile' does not match its folder name '$($selectedSkill.Name)'."
    }
    if ([string]::IsNullOrWhiteSpace($descriptionMatch.Groups[1].Value)) {
        throw "Skill description is empty in '$skillFile'."
    }

    $archivePath = Join-Path $outputPath "$($selectedSkill.Name).zip"
    if (Test-Path -LiteralPath $archivePath) {
        Remove-Item -LiteralPath $archivePath -Force
    }
    $archive = [System.IO.Compression.ZipFile]::Open(
        $archivePath,
        [System.IO.Compression.ZipArchiveMode]::Create
    )
    try {
        $skillRoot = $selectedSkill.FullName.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
        $files = Get-ChildItem -LiteralPath $selectedSkill.FullName -File -Recurse |
            Where-Object {
                $relativePath = $_.FullName.Substring($skillRoot.Length)
                $pathParts = $relativePath -split '[\\/]'
                $pathParts -notcontains '__pycache__' -and
                    $_.Name -notin @('.DS_Store', 'Thumbs.db', 'desktop.ini') -and
                    $_.Extension -notin @('.pyc', '.pyo')
            }

        foreach ($file in $files) {
            $relativePath = $file.FullName.Substring($skillRoot.Length).Replace('\', '/')
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $archive,
                $file.FullName,
                $relativePath,
                [System.IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
        }

        $archive.Dispose()
        $archive = [System.IO.Compression.ZipFile]::OpenRead($archivePath)
        if (-not ($archive.Entries | Where-Object FullName -EQ 'SKILL.md')) {
            throw "Packaged archive '$archivePath' does not contain SKILL.md at its root."
        }
        $transientEntry = $archive.Entries |
            Where-Object {
                $_.FullName -match '(^|/)(__pycache__/|[^/]+\.(pyc|pyo)$|\.DS_Store$|Thumbs\.db$|desktop\.ini$)'
            } |
            Select-Object -First 1
        if ($transientEntry) {
            throw "Packaged archive '$archivePath' contains transient file '$($transientEntry.FullName)'."
        }
    }
    finally {
        $archive.Dispose()
    }

    Write-Output "Packaged $($selectedSkill.Name) -> $archivePath"
}
