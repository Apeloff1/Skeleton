/**
 * First-install host commands, per host shell.
 *
 * The POSIX commands are the canonical production-assembly commands and stay
 * byte-identical. Windows PowerShell equivalents are written out explicitly
 * (no regex rewriting), and a step that the scripts do not support on native
 * Windows says so and points at WSL 2 instead of showing a command that
 * would fail.
 */
export type HostShell = 'posix' | 'powershell' | 'wsl';

export const HOST_SHELLS: readonly { id: HostShell; label: string; hint: string }[] = [
  { id: 'posix', label: 'macOS / Linux', hint: 'Terminal with bash or zsh' },
  { id: 'powershell', label: 'Windows', hint: 'PowerShell with the py launcher' },
  { id: 'wsl', label: 'Windows + WSL 2', hint: 'Ubuntu on WSL 2 runs the macOS / Linux commands unchanged' },
];

export interface SetupCommand {
  title: string;
  text: string;
  posix: string;
  /** null: not supported on native Windows; use WSL 2. */
  powershell: string | null;
  /** Extra host-specific caveat for native Windows. */
  windowsNote?: string;
}

const PS = 'py -3';

export const SETUP_COMMANDS: readonly SetupCommand[] = [
  {
    title: 'Launch Jeeves offline desktop',
    posix: 'python scripts/launch_jeeves_desktop.py',
    powershell: `${PS} scripts\\launch_jeeves_desktop.py`,
    text: 'Open the independent native Jeeves workbench on your computer. Select the installed GGUF and approved private SQLite state. This runs local inference without an external provider or network service; it does not replace protected canonical backend qualification for the mobile client.',
  },
  {
    title: 'Create Jeeves local model manifest',
    posix: 'python scripts/build_jeeves_local_manifest.py --model /ABSOLUTE/OWNED_MODEL.gguf --executable /ABSOLUTE/llama-cli --output /ABSOLUTE/jeeves.json --profile qwen3-completion-chat',
    powershell: `${PS} scripts\\build_jeeves_local_manifest.py --model C:\\ABSOLUTE\\OWNED_MODEL.gguf --executable C:\\ABSOLUTE\\llama-cli.exe --output C:\\ABSOLUTE\\jeeves.json --profile qwen3-completion-chat`,
    text: 'Use an already-owned licensed GGUF and compatible real llama.cpp executable. This creates a digest-pinned, read-only deployment identity named jeeves. It does not download weights or pretend that Jeeves was newly trained.',
  },
  {
    title: 'Execute a real local model completion',
    posix: 'python scripts/install_ai_chat.py --deployment /ABSOLUTE/jeeves.json --live-local',
    powershell: `${PS} scripts\\install_ai_chat.py --deployment C:\\ABSOLUTE\\jeeves.json --live-local`,
    text: 'Runs the pinned local model process on your host; a passing result must include a real bound local output receipt. This proves host inference only, not protected app readiness.',
  },
  {
    title: 'Configure Jeeves as the only local primary AI',
    posix: 'python scripts/install_ai_chat.py --deployment /ABSOLUTE/jeeves.json --apply',
    powershell: `${PS} scripts\\install_ai_chat.py --deployment C:\\ABSOLUTE\\jeeves.json --apply`,
    text: 'Creates a private Compose configuration with local-only engine and backend, model_id=jeeves, no hosted fallback, and mandatory protected inference guard. For an existing private .env, explicitly add --force.',
  },
  {
    title: 'Start Jeeves, the backend and storage',
    posix: 'python scripts/install_ai_chat.py --deployment /ABSOLUTE/jeeves.json --apply --force --start',
    powershell: `${PS} scripts\\install_ai_chat.py --deployment C:\\ABSOLUTE\\jeeves.json --apply --force --start`,
    windowsNote: 'Needs Docker Desktop running with the WSL 2 engine. Windows startup is not yet covered by installer qualification.',
    text: 'Starts the local model stack with pinned read-only mounts. Docker startup does not mean an AI answered; the trusted local tokenizer, reviewer and canonical writer bootstrap are required.',
  },
  {
    title: 'Verify a genuine local-only Jeeves conversation',
    posix: 'python scripts/ai_chat_installed_smoke.py --base-url https://YOUR_BACKEND_HOST --login-email owner@example.com --exercise',
    powershell: `${PS} scripts\\ai_chat_installed_smoke.py --base-url https://YOUR_BACKEND_HOST --login-email owner@example.com --exercise`,
    text: 'Checks one actual authenticated turn using only provider_id=local and model_id=jeeves, verifies local provider receipts, durable assistant persistence and exact-key replay. No remote model fallback.',
  },
  {
    title: 'Recover a saved reply without generating again',
    posix: 'python scripts/ai_chat_installed_smoke.py --base-url https://YOUR_BACKEND_HOST --login-email owner@example.com --recover-thread THREAD_ID --recover-request REQUEST_ID',
    powershell: `${PS} scripts\\ai_chat_installed_smoke.py --base-url https://YOUR_BACKEND_HOST --login-email owner@example.com --recover-thread THREAD_ID --recover-request REQUEST_ID`,
    text: 'Reads the original turn and its local provider receipt only. A dropped connection must never cause a duplicate model run or a switch to another model.',
  },
  {
    title: 'Build a connected Jeeves Android client',
    posix: 'cd frontend && EXPO_PUBLIC_BACKEND_URL=https://YOUR_BACKEND_HOST npx eas build --profile apk --platform android',
    powershell: 'cd frontend; $env:EXPO_PUBLIC_BACKEND_URL = "https://YOUR_BACKEND_HOST"; npx eas build --profile apk --platform android',
    text: 'The local GGUF runs on your computer/server, NOT inside the phone. The phone connects to your own authenticated HTTPS backend, never to an external model provider.',
  },
  {
    title: 'Inspect the protected runtime',
    posix: 'python -m skeleton app doctor --live --studio --json',
    powershell: `${PS} -m skeleton app doctor --live --studio --json`,
    text: 'Check storage, engine, local model, protected tokenizer/snapshot/reviewer and device prerequisites individually. Healthy HTTP is not model inference.',
  },
  {
    title: 'Optional explicit model acquisition',
    posix: 'python scripts/provision_local_ai.py --help',
    powershell: null,
    windowsNote: 'Model provisioning checks POSIX file ownership and is not supported on native Windows. Run it from WSL 2, or supply already-owned files.',
    text: 'Model acquisition is separate from inference. You may supply already-owned files for completely offline setup. Downloads require explicit operator consent and do not make the model active.',
  },
];

export interface ShownCommand {
  title: string;
  text: string;
  /** Command for the chosen shell, or null when that shell cannot run it. */
  command: string | null;
  note: string | null;
}

export function commandsFor(shell: HostShell): ShownCommand[] {
  return SETUP_COMMANDS.map((item) => {
    if (shell === 'powershell') {
      return {
        title: item.title,
        text: item.text,
        command: item.powershell,
        note: item.windowsNote ?? null,
      };
    }
    return { title: item.title, text: item.text, command: item.posix, note: null };
  });
}

/** Best-effort guess of the *host* shell. On a phone the host is a different
 * computer, so native platforms fall back to macOS / Linux and the user picks. */
export function detectHostShell(
  platformOs: string,
  nav?: { platform?: string; userAgent?: string; userAgentData?: { platform?: string } } | null,
): HostShell {
  if (platformOs !== 'web' || !nav) return 'posix';
  const hint = (nav.userAgentData?.platform || nav.platform || nav.userAgent || '').toLowerCase();
  return hint.includes('win') ? 'powershell' : 'posix';
}

export const HOST_SHELL_COPY: Record<HostShell, string> = {
  posix: 'These commands run in a terminal on your host from the repository root.',
  powershell: 'These PowerShell commands run from the repository root. Install Python 3.11+ from python.org so the py launcher is available. Native Windows hosting is not fully qualified yet; WSL 2 is the most complete path today.',
  wsl: 'Open Ubuntu on WSL 2, clone the repository inside the Linux filesystem (not /mnt/c), and run the macOS / Linux commands unchanged.',
};
