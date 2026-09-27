# Reproducible vector artwork rendered with Windows GDI+. No downloaded artwork.
# Run after changing the mark; generated PNG/ICO resources are checked in.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$assetsDir = Join-Path $repoRoot 'packaging\windows\msix\Assets'
New-Item -ItemType Directory -Path $assetsDir -Force | Out-Null

function New-BrandBitmap {
    param([int]$Width, [int]$Height)
    $scale = 4
    $bitmap = [System.Drawing.Bitmap]::new($Width * $scale, $Height * $scale)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.Clear([System.Drawing.Color]::Transparent)
    $size = [single]([Math]::Min($Width, $Height) * $scale)
    $left = [single](($Width * $scale - $size) / 2)
    $top = [single](($Height * $scale - $size) / 2)
    $graphics.TranslateTransform($left, $top)
    $graphics.ScaleTransform(($size / 100), ($size / 100))
    $background = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml('#111C33'))
    $cyan = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml('#55E1E8'))
    $white = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml('#E8F5FF'))
    $lines = [System.Drawing.Pen]::new([System.Drawing.ColorTranslator]::FromHtml('#669BFF'), 2.6)
    $lines.StartCap = $lines.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $border = [System.Drawing.Pen]::new([System.Drawing.ColorTranslator]::FromHtml('#2F496E'), 1)
    $shape = [System.Drawing.Drawing2D.GraphicsPath]::new()
    foreach ($corner in @(@(3, 3, 180), @(73, 3, 270), @(73, 73, 0), @(3, 73, 90))) {
        $shape.AddArc([single]$corner[0], [single]$corner[1], 24, 24, [single]$corner[2], 90)
    }
    $shape.CloseFigure()
    $graphics.FillPath($background, $shape)
    $graphics.DrawPath($border, $shape)
    # Wrist followed by four joints on each of the five fingers.
    $points = @(
        @(51, 81), @(38, 69), @(30, 59), @(23, 50), @(19, 42),
        @(41, 58), @(38, 43), @(36, 31), @(35, 21),
        @(51, 56), @(51, 39), @(51, 26), @(51, 16),
        @(61, 59), @(64, 44), @(66, 33), @(67, 24),
        @(70, 65), @(76, 55), @(79, 46), @(82, 38)
    )
    $chains = @(@(0,1,2,3,4), @(0,5,6,7,8), @(5,9,10,11,12), @(9,13,14,15,16), @(13,17,18,19,20), @(0,17))
    foreach ($chain in $chains) {
        for ($i = 1; $i -lt $chain.Length; $i++) {
            $a = $points[$chain[$i - 1]]; $b = $points[$chain[$i]]
            $graphics.DrawLine($lines, [single]$a[0], [single]$a[1], [single]$b[0], [single]$b[1])
        }
    }
    for ($i = 0; $i -lt $points.Length; $i++) {
        $tip = $i -in @(4, 8, 12, 16, 20)
        $radius = if ($tip) { 2.5 } else { 1.6 }
        $brush = if ($tip) { $white } else { $cyan }
        $graphics.FillEllipse($brush, [single]($points[$i][0] - $radius), [single]($points[$i][1] - $radius), [single](2 * $radius), [single](2 * $radius))
    }
    $graphics.Dispose(); $shape.Dispose(); $background.Dispose(); $cyan.Dispose(); $white.Dispose(); $lines.Dispose(); $border.Dispose()
    $output = [System.Drawing.Bitmap]::new($Width, $Height)
    $resizer = [System.Drawing.Graphics]::FromImage($output)
    $resizer.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $resizer.DrawImage($bitmap, 0, 0, $Width, $Height)
    $resizer.Dispose(); $bitmap.Dispose()
    return $output
}

$resources = @{
    'StoreLogo.png' = @(50, 50)
    'Square44x44Logo.png' = @(44, 44)
    'Square150x150Logo.png' = @(150, 150)
    'Wide310x150Logo.png' = @(310, 150)
    'Square310x310Logo.png' = @(310, 310)
    'SplashScreen.png' = @(620, 300)
}
foreach ($name in $resources.Keys) {
    $bitmap = New-BrandBitmap $resources[$name][0] $resources[$name][1]
    $bitmap.Save((Join-Path $assetsDir $name), [System.Drawing.Imaging.ImageFormat]::Png)
    $bitmap.Dispose()
}

# An ICO directory with PNG-compressed frames preserves sharp Windows taskbar sizes.
$sizes = @(16, 24, 32, 48, 64, 128, 256)
$frames = @()
foreach ($size in $sizes) {
    $bitmap = New-BrandBitmap $size $size
    $stream = [System.IO.MemoryStream]::new()
    $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
    $frames += ,($stream.ToArray())
    $stream.Dispose(); $bitmap.Dispose()
}
$icoPath = Join-Path $repoRoot 'packaging\windows\SmartGestureOS.ico'
$writer = [System.IO.BinaryWriter]::new([System.IO.File]::Create($icoPath))
try {
    $writer.Write([uint16]0); $writer.Write([uint16]1); $writer.Write([uint16]$sizes.Length)
    $offset = 6 + 16 * $sizes.Length
    for ($i = 0; $i -lt $sizes.Length; $i++) {
        $dimension = if ($sizes[$i] -eq 256) { 0 } else { $sizes[$i] }
        $writer.Write([byte]$dimension); $writer.Write([byte]$dimension)
        $writer.Write([byte]0); $writer.Write([byte]0)
        $writer.Write([uint16]1); $writer.Write([uint16]32)
        $writer.Write([uint32]$frames[$i].Length); $writer.Write([uint32]$offset)
        $offset += $frames[$i].Length
    }
    foreach ($frame in $frames) { $writer.Write([byte[]]$frame) }
} finally { $writer.Dispose() }
Write-Host "Generated six MSIX PNG assets and $icoPath"
