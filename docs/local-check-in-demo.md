# Optional local check-in demo

Google Forms is the primary daily route; see the [collection protocol](data-collection-protocol.md).
This service remains a local development demonstration, not a prerequisite for collection.

## Run on the desktop

From the repository directory in PowerShell:

```powershell
$studyDatabase = Join-Path $env:LOCALAPPDATA 'AIHealthCoach/study.sqlite3'
uv run python -m ai_health_coach --serve-checkins --database $studyDatabase --timezone America/Los_Angeles
```

Open the printed session link in a browser. The terminal owns the service;
Ctrl+C stops it. Reopen the new session link after restarting. The same database
retains previous check-ins and configuration snapshots. Use an explicit absolute
database path outside every Git checkout on other operating systems.

The page asks for a rating rather than preselecting one. Choose skipped or missing
to record an absent rating. Wake time is optional; an afternoon entry without it
is kept as unanchored. The time the rating describes and the server's capture time
are stored separately. Earlier ratings can be recorded without hiding the delay.
Check "I'm recording this late" when relevant. Automatic window timing uses the
capture instant; manual events retain `manual` timing and their capture delay.
At a repeated DST hour, choose the first or second occurrence for the rating and
wake time independently. Each option shows its UTC offset. The initial current
time preserves the actual occurrence automatically. Nonexistent local DST times
are rejected.

The form uses the device timezone to interpret entered times and displays it next
to the study timezone. Storage normalizes the resulting instant to the study
timezone. Set the device timezone correctly before recording past entries.

Change afternoon boundaries with `--afternoon-start-hours 4 --afternoon-end-hours 8`
if desired. All hours are elapsed from the actual wake instant, including across
DST changes. Wake and day-close have no fixed clock schedule. No reminders or
background collection run automatically.

To record caffeine context, add `--caffeine-cutoff HH:MM`, using 24-hour time in
the study timezone. For example, `--caffeine-cutoff 14:00` defines a threshold of
14:00; choose your own threshold rather than treating this example as health
advice. The answer describes caffeine consumed at or after that time on the
rating's study-local date. Without a configured cutoff, the field stays disabled
and missing. Changes create a new configuration snapshot; old entries keep their
original threshold.

## iPhone over a private network

This Windows-to-iPhone route uses a local development certificate. The program
does not install certificates or change firewall rules. The instructions below
follow the upstream setup documentation; an actual iPhone connection still needs
to be verified on your network.

1. Verify the desktop loopback flow above. Connect both devices to your own trusted
   private network, not a guest or campus network that isolates devices. In
   PowerShell, inspect `Get-NetIPConfiguration` and `Get-NetConnectionProfile`.
   Identify the active adapter's private IPv4 address and verify its Windows
   network category is Private. Reserve that address in your router if possible;
   if it changes, recreate the certificate and restart with the new address.
2. Install [mkcert](https://github.com/FiloSottile/mkcert#installation). On Windows,
   download the matching Windows executable from its
   [official releases](https://github.com/FiloSottile/mkcert/releases), rename it
   `mkcert.exe`, put it in a private tools directory, and add that directory to
   your user PATH. Reopen
   PowerShell and confirm `mkcert -version` works before proceeding.
3. Create the certificate outside Git, in a normal PowerShell window. Replace the
   example address before running this block. Stop on any error. `mkcert -install`
   adds a local certificate authority to your computer's trust store and may ask
   for administrator approval.

```powershell
$studyDatabase = Join-Path $env:LOCALAPPDATA 'AIHealthCoach/study.sqlite3'
$computerIp = '192.168.1.20' # Replace with this computer's private IPv4 address.
$certificate = Join-Path $env:LOCALAPPDATA 'AIHealthCoach/cert.pem'
$privateKey = Join-Path $env:LOCALAPPDATA 'AIHealthCoach/key.pem'
New-Item -ItemType Directory -Force -Path (Split-Path $certificate) | Out-Null
mkcert -install
if ($LASTEXITCODE -ne 0) { throw 'Certificate authority installation failed' }
mkcert -cert-file $certificate -key-file $privateKey $computerIp
if ($LASTEXITCODE -ne 0) { throw 'Certificate creation failed' }
$certificateAuthorityDirectory = mkcert -CAROOT
if ($LASTEXITCODE -ne 0) { throw 'Could not locate the certificate authority' }
Join-Path $certificateAuthorityDirectory 'rootCA.pem'
```

4. Transfer only that `rootCA.pem` certificate to your iPhone, for example as a
   private email attachment. Never transfer `rootCA-key.pem` or `key.pem`; the CA
   key can mint certificates trusted by these devices. Open the certificate on
   the phone, then [install its profile](https://support.apple.com/en-us/102400)
   through Settings > Profile Downloaded > Install. Following
   [Apple's trust instructions](https://support.apple.com/en-us/102390), enable it
   in Settings > General > About > Certificate Trust Settings. Trust only the
   certificate you just created.
5. In a separate **administrator PowerShell** window, add this narrowly scoped
   [Windows firewall rule](https://learn.microsoft.com/en-us/powershell/module/netsecurity/new-netfirewallrule).
   If the named rule already exists, inspect it rather than creating a duplicate.

```powershell
New-NetFirewallRule -Name 'AIHealthCoach-Checkins' -DisplayName 'AI Health Coach check-ins' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765 -Profile Private -RemoteAddress LocalSubnet -EdgeTraversalPolicy Block
```

6. Back in a normal PowerShell window **in the repository directory**, start the
   service. These variables are repeated so this block works in a new window.

```powershell
$studyDatabase = Join-Path $env:LOCALAPPDATA 'AIHealthCoach/study.sqlite3'
$computerIp = '192.168.1.20' # Replace with the address used in the certificate.
$certificate = Join-Path $env:LOCALAPPDATA 'AIHealthCoach/cert.pem'
$privateKey = Join-Path $env:LOCALAPPDATA 'AIHealthCoach/key.pem'
uv run python -m ai_health_coach --serve-checkins --database $studyDatabase --timezone America/Los_Angeles --bind $computerIp --cert $certificate --key $privateKey
```

7. Open the exact printed session link in Safari, including its `#token=...`
   fragment. Verify the page loads without a certificate warning and submit an
   entry; it should display "Saved at". Keep the terminal running. If it times
   out, check the address, network category, firewall rule, and device isolation.
   For a certificate warning, check the certificate's address and iPhone root
   trust; do not bypass the warning. For "Session unavailable," reopen the current
   printed link rather than refreshing the token-free page.

Do not forward the port through your router or allow it on Public networks. To
remove phone access, stop the service with Ctrl+C and run
`Remove-NetFirewallRule -Name 'AIHealthCoach-Checkins'` in administrator PowerShell.
When no longer needed, remove the mkcert profile from the iPhone and run
`mkcert -uninstall` on the computer; first check that no other development project
uses the same CA. The session link is a credential; share it only with your phone.
