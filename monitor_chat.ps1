# monitor_chat.ps1
# Script para monitorar as respostas do chat e enviar automaticamente o proximo passo
# Foca na janela do Antigravity (VS Code / IDE) e digita o comando.
# NOTA: Deixe o cursor de texto posicionado na caixa de texto do chat do Antigravity.

$transcriptPath = "C:\Users\wand\.gemini\antigravity\brain\d8c3ae3b-2659-4ae3-9e34-fdfd92af37e4\.system_generated\logs\transcript.jsonl"
$wshell = New-Object -ComObject WScript.Shell

Write-Host "==========================================================" -ForegroundColor Green
Write-Host "   MONITOR DE CHAT VASP - MODO CONTINUO (PRIORIDADE)     " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "-> Monitorando: $transcriptPath" -ForegroundColor White

function EnviarComando {
    Write-Host "Buscando janela correta do Antigravity/VASP..." -ForegroundColor Cyan
    
    # 1. Prioridade absoluta: Buscar janela que contenha a pasta ou termo da extensao
    $targetProc = Get-Process | Where-Object { 
        $_.MainWindowTitle -match "workflow-vasp" -or
        $_.MainWindowTitle -match "antigravity" -or
        $_.MainWindowTitle -match "Antigravity"
    } | Select-Object -First 1

    # 2. Fallback: Qualquer janela do VS Code
    if (-not $targetProc) {
        $targetProc = Get-Process | Where-Object { $_.ProcessName -eq "Code" } | Select-Object -First 1
    }

    if ($targetProc) {
        Write-Host "Focando na janela: $($targetProc.MainWindowTitle) (PID: $($targetProc.Id))..." -ForegroundColor Gray
        [void]$wshell.AppActivate($targetProc.Id)
        Start-Sleep -Milliseconds 1000
    } else {
        Write-Host "AVISO: Janela do VS Code nao encontrada. Certifique-se de que o chat esta focado!" -ForegroundColor Yellow
    }
    
    Write-Host "Digitando o comando..." -ForegroundColor Gray
    $wshell.SendKeys("/goal faca as etapas seguintes ate as 08:00 de amanha.")
    Start-Sleep -Milliseconds 500
    $wshell.SendKeys("{ENTER}")
    Write-Host "Comando enviado com sucesso!" -ForegroundColor Green
}

# Inicializa o contador de linhas
$lastCount = 0
if (Test-Path $transcriptPath) {
    $lines = Get-Content $transcriptPath
    $lastCount = $lines.Length
    
    # Bootstrap Check: Se a ultima linha ja for do MODEL, dispara imediatamente
    if ($lastCount -gt 0) {
        $lastLine = $lines[-1]
        if ($lastLine -match '"source":"MODEL"' -or $lastLine -match '"type":"PLANNER_RESPONSE"' -or $lastLine -match '"type":"FINAL_RESPONSE"') {
            Write-Host "Ultima resposta no log ja e do Assistente. Disparando imediatamente..." -ForegroundColor Yellow
            EnviarComando
            Start-Sleep -Seconds 15
            # Recarrega contador de linhas apos digitar
            $lines = Get-Content $transcriptPath
            $lastCount = $lines.Length
        }
    }
}

Write-Host "Aguardando proxima resposta do assistente..." -ForegroundColor Gray

while ($true) {
    Start-Sleep -Seconds 5
    if (Test-Path $transcriptPath) {
        $lines = Get-Content $transcriptPath
        $currentCount = $lines.Length
        
        if ($currentCount -gt $lastCount) {
            $lastLine = $lines[-1]
            
            if ($lastLine -match '"source":"MODEL"' -or $lastLine -match '"type":"PLANNER_RESPONSE"' -or $lastLine -match '"type":"FINAL_RESPONSE"') {
                Write-Host "Assistente concluiu a etapa! Preparando envio..." -ForegroundColor Cyan
                Start-Sleep -Seconds 5
                EnviarComando
                
                # Aguarda o log registrar a mensagem digitada para atualizar o cursor
                Start-Sleep -Seconds 15
                $lines = Get-Content $transcriptPath
                $currentCount = $lines.Length
            }
            $lastCount = $currentCount
        }
    }
}
