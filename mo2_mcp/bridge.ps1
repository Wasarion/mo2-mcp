# MCP bridge for MO2: an MCP client (e.g. the Claude desktop app) talks MCP over stdin/stdout,
# this script forwards each message to the MO2 plugin on 127.0.0.1.
# When MO2 is closed it answers by itself so the desktop app keeps the tools listed.

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$connFile = Join-Path $here 'connection.json'
$toolsFile = Join-Path $here 'tools.json'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$stdin = New-Object System.IO.StreamReader([Console]::OpenStandardInput(), $utf8)
$stdout = New-Object System.IO.StreamWriter([Console]::OpenStandardOutput(), $utf8)
$stdout.AutoFlush = $true
$stdout.NewLine = "`n"

Add-Type -AssemblyName System.Net.Http
$client = New-Object System.Net.Http.HttpClient
$client.Timeout = [TimeSpan]::FromMinutes(40)

function Log([string]$text) { [Console]::Error.WriteLine("mo2-bridge: $text") }

function Send-ToMO2([string]$line) {
    $conn = [IO.File]::ReadAllText($connFile, $utf8) | ConvertFrom-Json
    $req = New-Object System.Net.Http.HttpRequestMessage([System.Net.Http.HttpMethod]::Post, "http://127.0.0.1:$($conn.port)/mcp")
    [void]$req.Headers.TryAddWithoutValidation('X-MO2-Token', [string]$conn.token)
    $req.Content = New-Object System.Net.Http.StringContent($line, $utf8, 'application/json')
    $resp = $client.SendAsync($req).GetAwaiter().GetResult()
    $code = [int]$resp.StatusCode
    if ($code -eq 202) { return '' }
    if ($code -ne 200) { throw "MO2 plugin answered HTTP $code" }
    return $utf8.GetString($resp.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult())
}

function Reply-Offline([string]$line, [string]$why) {
    try { $msg = $line | ConvertFrom-Json } catch { return '' }
    if ($null -eq $msg.PSObject.Properties['id'] -or $null -eq $msg.method) { return '' }
    $id = ConvertTo-Json -InputObject $msg.id -Compress
    switch ([string]$msg.method) {
        'initialize' {
            $ver = [string]$msg.params.protocolVersion
            if (-not $ver) { $ver = '2025-06-18' }
            $verJson = ConvertTo-Json -InputObject $ver -Compress
            return '{"jsonrpc":"2.0","id":' + $id + ',"result":{"protocolVersion":' + $verJson + ',"capabilities":{"tools":{"listChanged":false}},"serverInfo":{"name":"mo2","version":"bridge"},"instructions":"MO2 is not running right now; tools work once the user starts MO2."}}'
        }
        'ping' { return '{"jsonrpc":"2.0","id":' + $id + ',"result":{}}' }
        'tools/list' {
            $tools = '[]'
            if (Test-Path $toolsFile) { $tools = [IO.File]::ReadAllText($toolsFile, $utf8).Trim() }
            return '{"jsonrpc":"2.0","id":' + $id + ',"result":{"tools":' + $tools + '}}'
        }
        'tools/call' {
            $text = ConvertTo-Json -InputObject "MO2 is not reachable ($why). Start Mod Organizer 2 (with the Claude MCP Server plugin enabled) and try again." -Compress
            return '{"jsonrpc":"2.0","id":' + $id + ',"result":{"content":[{"type":"text","text":' + $text + '}],"isError":true}}'
        }
        default {
            return '{"jsonrpc":"2.0","id":' + $id + ',"error":{"code":-32601,"message":"MO2 is not running"}}'
        }
    }
}

Log 'started'
while ($null -ne ($line = $stdin.ReadLine())) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    try {
        $reply = Send-ToMO2 $line
    } catch {
        $why = $_.Exception.GetBaseException().Message
        Log "offline reply: $why"
        $reply = Reply-Offline $line $why
    }
    if ($reply) { $stdout.WriteLine($reply.Trim()) }
}
Log 'stdin closed, exiting'
