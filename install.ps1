# install.ps1 —— 把 wechat-archive 装进 DSH 的技能目录
$ErrorActionPreference = 'Stop'
$src = Split-Path -Parent $MyInvocation.MyCommand.Path
$dst = Join-Path $env:USERPROFILE '.agents/skills/wechat-archive'
$py = (Get-Command python -ErrorAction Stop).Source

"source: $src"
"target: $dst"
"python: $py"

if (Test-Path -LiteralPath $dst) {
  "目标已存在，先备份为 $dst.bak"
  if (Test-Path -LiteralPath "$dst.bak") { Remove-Item -LiteralPath "$dst.bak" -Recurse -Force }
  Move-Item -LiteralPath $dst -Destination "$dst.bak"
}
New-Item -ItemType Directory -Path $dst -Force | Out-Null
Copy-Item -Path (Join-Path $src '*') -Destination $dst -Recurse -Force

& $py (Join-Path $dst 'scripts/doctor.py')
""
"装好了。重启 DSH 后技能列表会出现 wechat-archive。"
"卸载：Remove-Item -LiteralPath '$dst' -Recurse -Force"
