# Tests for start_llama.ps1
# Run with: Invoke-Pester -Path llama.cpp/tests/start_llama.Tests.ps1

Describe "start_llama.ps1 configuration" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot "..\start_llama.ps1"
        $scriptContent = Get-Content $scriptPath -Raw
    }

    It "defines LLAMA_PATH" {
        $scriptContent | Should -Match 'LLAMA_PATH\s*='
    }

    It "defines INI_PATH" {
        $scriptContent | Should -Match 'INI_PATH\s*='
    }

    It "defines EMBED_MODEL" {
        $scriptContent | Should -Match 'EMBED_MODEL\s*='
    }

    It "sets ErrorActionPreference to Stop" {
        $scriptContent | Should -Match 'ErrorActionPreference\s*=\s*"Stop"'
    }

    It "registers a trap for Ctrl+C handling" {
        $scriptContent | Should -Match 'trap\s*\{'
    }

    It "uses a finally block for cleanup guarantee" {
        $scriptContent | Should -Match 'finally\s*\{'
    }
}

Describe "start_llama.ps1 server arguments" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot "..\start_llama.ps1"
        $scriptContent = Get-Content $scriptPath -Raw
    }

    Context "Embedding server" {
        It "starts on port 8081" {
            $scriptContent | Should -Match '"--port",\s*"8081"'
        }

        It "runs in embedding mode" {
            $scriptContent | Should -Match '"--embedding"'
        }

        It "uses CLS pooling" {
            $scriptContent | Should -Match '"--pooling",\s*"cls"'
        }

        It "sets context size to 8192" {
            $scriptContent | Should -Match '"-c",\s*"8192"'
        }

        It "offloads all layers to GPU" {
            $scriptContent | Should -Match '"-ngl",\s*"99"'
        }

        It "disables memory mapping" {
            $scriptContent | Should -Match '"--no-mmap"'
        }
    }

    Context "Chat router server" {
        It "starts on port 8080" {
            $scriptContent | Should -Match '"--port",\s*"8080"'
        }

        It "uses models-preset config" {
            $scriptContent | Should -Match '"--models-preset"'
        }

        It "limits to 1 model max for swapping" {
            $scriptContent | Should -Match '"--models-max",\s*"1"'
        }
    }
}

Describe "start_llama.ps1 process management" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot "..\start_llama.ps1"
        $scriptContent = Get-Content $scriptPath -Raw
    }

    It "uses Start-Process with PassThru to track processes" {
        $scriptContent | Should -Match 'Start-Process.*-PassThru'
    }

    It "initializes embeddingProcess variable" {
        $scriptContent | Should -Match '\$embeddingProcess\s*=\s*\$null'
    }

    It "initializes chatProcess variable" {
        $scriptContent | Should -Match '\$chatProcess\s*=\s*\$null'
    }

    It "checks HasExited for both processes in the main loop" {
        $scriptContent | Should -Match 'HasExited'
    }

    It "calls Kill on processes during cleanup" {
        $scriptContent | Should -Match '\.Kill\(\)'
    }

    It "waits for process exit after kill" {
        $scriptContent | Should -Match '\.WaitForExit\(\)'
    }

    It "uses NoNewWindow to keep output in console" {
        $scriptContent | Should -Match '-NoNewWindow'
    }
}

Describe "start_llama.ps1 cleanup logic" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot "..\start_llama.ps1"
        $scriptContent = Get-Content $scriptPath -Raw
    }

    It "defines a cleanup scriptblock" {
        $scriptContent | Should -Match '\$cleanup\s*=\s*\{'
    }

    It "checks chatProcess before killing" {
        $scriptContent | Should -Match 'chatProcess.*HasExited'
    }

    It "checks embeddingProcess before killing" {
        $scriptContent | Should -Match 'embeddingProcess.*HasExited'
    }

    It "registers PowerShell.Exiting event for window close" {
        $scriptContent | Should -Match 'Register-EngineEvent\s+PowerShell\.Exiting'
    }
}

Describe "start_llama.bat delegation" {
    BeforeAll {
        $batPath = Join-Path $PSScriptRoot "..\start_llama.bat"
        $batContent = Get-Content $batPath -Raw
    }

    It "delegates to PowerShell" {
        $batContent | Should -Match 'powershell'
    }

    It "sets ExecutionPolicy Bypass" {
        $batContent | Should -Match 'ExecutionPolicy\s+Bypass'
    }

    It "references start_llama.ps1" {
        $batContent | Should -Match 'start_llama\.ps1'
    }

    It "uses script directory-relative path" {
        $batContent | Should -Match '%~dp0'
    }
}
