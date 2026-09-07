<#
  embed-photo.ps1 — вшивает фото в index.html как base64.

  Зачем: страница должна оставаться одним самодостаточным файлом, поэтому фото
  хранится прямо в CONFIG.photo — крупная копия для аватара и лёгкая для vCard.
  Скрипт вырезает квадрат, масштабирует, жмёт в JPEG и подставляет обе строки.

  Использование (для новой визитки: скопируйте index.html и запустите):

      .\embed-photo.ps1 -Photo "C:\path\to\photo.jpg"

  Кадр по умолчанию — квадрат по центру ширины, прижатый к верху (портрет).
  Если лицо уходит из круга, задайте область вручную (координаты в пикселях
  исходника): -CropX 300 -CropY 0 -CropSize 880
#>

param(
  [Parameter(Mandatory=$true)][string]$Photo,
  [string]$Html = (Join-Path $PSScriptRoot 'index.html'),

  [int]$CropX    = -1,   # -1 = вычислить автоматически
  [int]$CropY    = -1,
  [int]$CropSize = -1,

  [int]$AvatarSize    = 720,  # размер аватара на странице (с запасом под Retina)
  [int]$AvatarQuality = 86,
  [int]$VcardSize     = 320,  # фото в контакте: держим лёгким, ~15-20 КБ
  [int]$VcardQuality  = 76
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

if (-not (Test-Path $Photo)) { throw "Не найдено фото: $Photo" }
if (-not (Test-Path $Html))  { throw "Не найден HTML: $Html" }

$src = [System.Drawing.Image]::FromFile($Photo)

# --- Область кадрирования ---
if ($CropSize -lt 1) { $CropSize = [Math]::Min($src.Width, $src.Height) }
if ($CropX -lt 0)    { $CropX = [int](($src.Width - $CropSize) / 2) }   # по центру ширины
if ($CropY -lt 0)    { $CropY = 0 }                                     # от верха: голова в кадре

# --- Вырезаем квадрат и масштабируем в JPEG ---
function Convert-ToJpegBase64 {
  param([System.Drawing.Image]$Image, [int]$Size, [int]$Quality)

  $bmp = New-Object System.Drawing.Bitmap($Size, $Size)
  $bmp.SetResolution(72, 72)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
  $g.InterpolationMode  = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g.SmoothingMode      = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
  $g.PixelOffsetMode    = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
  $g.DrawImage($Image,
    (New-Object System.Drawing.Rectangle(0, 0, $Size, $Size)),
    $script:CropX, $script:CropY, $script:CropSize, $script:CropSize,
    [System.Drawing.GraphicsUnit]::Pixel)
  $g.Dispose()

  $codec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object { $_.MimeType -eq 'image/jpeg' }
  $ep = New-Object System.Drawing.Imaging.EncoderParameters(1)
  $ep.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter([System.Drawing.Imaging.Encoder]::Quality, [long]$Quality)

  $ms = New-Object System.IO.MemoryStream
  $bmp.Save($ms, $codec, $ep)
  $bytes = $ms.ToArray()
  $ms.Dispose(); $bmp.Dispose()

  return [Convert]::ToBase64String($bytes)
}

$avatarB64 = Convert-ToJpegBase64 -Image $src -Size $AvatarSize -Quality $AvatarQuality
$vcardB64  = Convert-ToJpegBase64 -Image $src -Size $VcardSize  -Quality $VcardQuality
$src.Dispose()

# --- Подставляем обе строки в CONFIG.photo ---
$text = [IO.File]::ReadAllText($Html, [Text.Encoding]::UTF8)

$pagePattern  = "(?<=page:\s{0,20}')data:image/jpeg;base64,[^']*(?=')"
$vcardPattern = "(?<=vcard:\s{0,20}')[^']*(?=')"

if (-not [regex]::IsMatch($text, $pagePattern))  { throw "Не найдено поле CONFIG.photo.page в $Html" }
if (-not [regex]::IsMatch($text, $vcardPattern)) { throw "Не найдено поле CONFIG.photo.vcard в $Html" }

$text = [regex]::Replace($text, $pagePattern,  "data:image/jpeg;base64,$avatarB64")
$text = [regex]::Replace($text, $vcardPattern, $vcardB64)

[IO.File]::WriteAllText($Html, $text, (New-Object Text.UTF8Encoding($false)))

Write-Output "Готово: $Html"
Write-Output ("  кадр    : x={0} y={1} размер={2}px из {3}" -f $CropX, $CropY, $CropSize, (Split-Path $Photo -Leaf))
Write-Output ("  аватар  : {0}x{0}px, ~{1} КБ base64" -f $AvatarSize, [Math]::Round($avatarB64.Length / 1024))
Write-Output ("  в vCard : {0}x{0}px, ~{1} КБ base64" -f $VcardSize,  [Math]::Round($vcardB64.Length / 1024))
