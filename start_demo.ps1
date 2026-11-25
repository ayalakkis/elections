# Starts the whole demonstration: the 3 blockchain ledger nodes and the election website.
# Usage (from this folder, in PowerShell):
#   .\start_demo.ps1          keep the existing votes
#   .\start_demo.ps1 -Fresh   start a brand new election (deletes the chains and the website database)
# First time only:  python -m pip install -r election_website\requirements.txt flask
param([switch]$Fresh)

$root  = $PSScriptRoot
$chain = Join-Path $root 'election__chain'
$web   = Join-Path $root 'election_website'
$env:DJANGO_DEBUG = 'True'    # local demonstration only
$env:SEND_OTP     = 'False'   # no SMS codes for the demo

if ($Fresh) {
    Remove-Item (Join-Path $chain '*_chain.json') -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $web 'db.sqlite3') -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $web 'media\candidates') -Recurse -ErrorAction SilentlyContinue
}

# Website database, demo election, and the voter register for the nodes.
Push-Location $web
python manage.py migrate
python manage.py seed_demo
Pop-Location

# One window per ledger node, so you can stop one during the demo (close its window).
foreach ($node in 'interior', 'commission', 'delegates') {
    Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$chain'; `$host.UI.RawUI.WindowTitle = 'Ledger node: $node'; python node.py $node"
}

# The website.
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$web'; `$env:DJANGO_DEBUG = 'True'; `$env:SEND_OTP = 'False'; `$host.UI.RawUI.WindowTitle = 'Election website'; python manage.py runserver 127.0.0.1:8000"

Start-Sleep -Seconds 5
Start-Process 'http://127.0.0.1:8000/'
Write-Host 'Election portal:  http://127.0.0.1:8000/          (vote, results, ledger explorer, control room)'
Write-Host 'Classic admin:    http://127.0.0.1:8000/account/  (manage voters, positions and candidates)'
Write-Host 'Demo accounts are listed in election_website\voting\management\commands\seed_demo.py'
