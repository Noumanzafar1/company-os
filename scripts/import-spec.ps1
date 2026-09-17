param([Parameter(Mandatory=$true)][string]$Source)
$sourceText = [IO.File]::ReadAllText($Source).Replace("`r`n", "`n")
$parts = [regex]::Split($sourceText, '(?m)(?=^# Part \d+ — )')
$mapping = @{
 '00-product-overview.md' = @(1,2,3); '01-system-context.md' = @(4);
 '02-architecture.md' = @(5,6); '03-domain-model.md' = @(7,8);
 '04-data-ownership.md' = @(9); '05-state-machines.md' = @(10);
 '06-events.md' = @(11); '07-jobs.md' = @(12); '08-policy-approvals.md' = @(13);
 '09-ai-gateway.md' = @(14); '10-agent-contracts.md' = @(15);
 '11-integrations.md' = @(16,17); '12-api.md' = @(18); '13-founder-console.md' = @(19);
 '14-security.md' = @(20); '15-observability.md' = @(21,22); '16-testing.md' = @(23);
 '17-deployment.md' = @(24); '18-development-workflow.md' = @(25);
 '19-implementation-roadmap.md' = @(28,29); '20-open-decisions.md' = @(30);
 'requirements.md' = @(27); 'adr/phase-1-registry.md' = @(26)
}
foreach($name in $mapping.Keys) {
 $content = ($mapping[$name] | ForEach-Object { $parts[$_] }) -join ''
 if($name -eq '00-product-overview.md') { $content = $parts[0] + $content }
 $target = Join-Path 'docs' $name
 [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($target))) | Out-Null
 [IO.File]::WriteAllText([IO.Path]::GetFullPath($target),$content,[Text.UTF8Encoding]::new($false))
}
Write-Output 'Mapped all 30 specification parts without changing requirement IDs.'
