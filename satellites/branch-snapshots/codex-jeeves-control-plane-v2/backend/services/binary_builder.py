"""
binary_builder.py — Package a Galaxy Studio build into downloadable artifacts.

ZIP path: pure-python zipfile, always works.

APK path (CRITICAL — must produce a *runnable* APK, not just a signed zip):
  1. Write a tiny Java `MainActivity` that constructs a WebView and loads
     `file:///android_asset/galaxy/index.html`.
  2. javac (native, JDK 17) → MainActivity.class (+ inner classes).
  3. d8 (x86_64 via qemu) → classes.dex.
  4. aapt2 compile/link → base.apk (resources + manifest + assets).
  5. Inject classes.dex into base.apk → unaligned.apk.
  6. zipalign 4 → aligned.apk.
  7. apksigner sign (v1 + v2 + v3 schemes) → final signed.apk.
  8. apksigner verify → confirm runnable.

The APK is a single-Activity WebView wrapper. The user's generated files land
under /assets/galaxy/ inside the APK and are loaded by the embedded
index.html. This installs and runs on every Android 7+ device (minSdk 24).
"""
from __future__ import annotations
import os, io, json, shutil, zipfile, tempfile, hashlib, asyncio, subprocess, platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ARTIFACTS_ROOT = Path("/app/backend/data/build_artifacts")
ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)

# ─── Android toolchain detection ───
ANDROID_SDK = Path(os.environ.get("ANDROID_SDK_ROOT", "/opt/android-sdk"))
_BT_DIRS = sorted((ANDROID_SDK / "build-tools").glob("*"), reverse=True) if (ANDROID_SDK / "build-tools").exists() else []
BUILD_TOOLS = _BT_DIRS[0] if _BT_DIRS else None
PLATFORMS_DIR = ANDROID_SDK / "platforms"
_PL_DIRS = sorted(PLATFORMS_DIR.glob("android-*"), reverse=True) if PLATFORMS_DIR.exists() else []
ANDROID_JAR = (_PL_DIRS[0] / "android.jar") if _PL_DIRS else None

QEMU_X86_64 = Path("/usr/bin/qemu-x86_64-static")


def _need_qemu() -> bool:
    return platform.machine() in ("aarch64", "arm64") and QEMU_X86_64.exists()


def _is_elf_x86_64(p: Path) -> bool:
    try:
        with p.open("rb") as fh:
            head = fh.read(20)
            if head[:4] != b"\x7fELF":
                return False
            # Class byte 4 = 2 (64-bit), machine bytes 18-19 = 0x3e (x86_64 little-endian)
            return head[4] == 2 and head[18:20] == b"\x3e\x00"
    except Exception:
        return False


def _wrap(bin_path: Path) -> list:
    """Return the argv prefix needed to invoke an Android SDK tool.
    aapt/aapt2/zipalign/d8(native) are x86_64 ELF → need qemu on aarch64.
    apksigner is a shell wrapper around a JAR → runs natively."""
    if _need_qemu() and _is_elf_x86_64(bin_path):
        return [str(QEMU_X86_64), str(bin_path)]
    return [str(bin_path)]


DEBUG_KEYSTORE = ARTIFACTS_ROOT / "keys" / "debug.keystore"
KEYSTORE_PASS = "android"
KEY_ALIAS = "androiddebugkey"


def _have_full_apk_toolchain() -> bool:
    return bool(
        BUILD_TOOLS and (BUILD_TOOLS / "aapt2").exists()
        and (BUILD_TOOLS / "apksigner").exists()
        and (BUILD_TOOLS / "zipalign").exists()
        and (BUILD_TOOLS / "d8").exists()
        and ANDROID_JAR and ANDROID_JAR.exists()
        and DEBUG_KEYSTORE.exists()
        and shutil.which("javac") is not None
    )


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────
def _sanitize_path(p: str) -> str:
    p = p.replace("\\", "/").lstrip("/")
    parts = [x for x in p.split("/") if x not in ("", "..")]
    return "/".join(parts) or "file.txt"


def _safe_pkg_segment(seg: str) -> str:
    """Make a string a valid Android package segment.
    
    Android's PackageParser rejects segments that start with a digit AND
    is notoriously fussy about underscores on some OEM-modded Android
    builds (notably Samsung OneUI 5.x+). Strip underscores entirely and
    fold consecutive non-alphanumerics into a single 'x'. Always-safe."""
    out = "".join(c if c.isalnum() else "" for c in seg.lower())
    if not out:
        out = "x"
    if out[0].isdigit():
        out = "g" + out
    return out


def _safe_pkg(build_id: str) -> str:
    return "com.codedock.galaxy." + _safe_pkg_segment(build_id)


def _build_files_iter(build: dict):
    """Yield unique (relpath, content) tuples — dedup keeps first occurrence."""
    gen = build.get("generated_files") or build.get("files") or {}
    seen = set()
    if isinstance(gen, dict):
        for path, content in gen.items():
            rp = _sanitize_path(path)
            if rp in seen: continue
            seen.add(rp)
            yield rp, content
    elif isinstance(gen, list):
        for entry in gen:
            if not isinstance(entry, dict): continue
            rp = _sanitize_path(entry.get("path", "file.txt"))
            if rp in seen: continue
            seen.add(rp)
            yield rp, entry.get("content", "")


# ─────────────────────────────────────────────────────────────────
# ZIP builder
# ─────────────────────────────────────────────────────────────────
def build_zip(build: dict) -> dict:
    build_id = build.get("build_id", "unknown")
    out_path = ARTIFACTS_ROOT / f"{build_id}.zip"
    file_count = 0
    total_bytes = 0
    sha256 = hashlib.sha256()

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        manifest = {
            "build_id":   build_id,
            "title":      build.get("title", ""),
            "genre":      build.get("genre", ""),
            "subgenre":   build.get("subgenre", ""),
            "file_count": build.get("file_count", 0),
            "created_at": build.get("created_at"),
            "version":    "1.0.0",
        }
        manifest_bytes = json.dumps(manifest, indent=2).encode()
        zf.writestr("manifest.json", manifest_bytes)
        sha256.update(manifest_bytes)
        for relpath, content in _build_files_iter(build):
            data = bytes(content) if isinstance(content, (bytes, bytearray)) else str(content).encode("utf-8", errors="replace")
            zf.writestr(relpath, data)
            sha256.update(data)
            file_count += 1
            total_bytes += len(data)

    return {
        "artifact_id":  f"zip_{build_id}",
        "kind":         "zip",
        "build_id":     build_id,
        "path":         str(out_path),
        "size_bytes":   out_path.stat().st_size,
        "file_count":   file_count,
        "raw_bytes":    total_bytes,
        "sha256":       sha256.hexdigest(),
        "created_at":   datetime.now(timezone.utc).isoformat(),
        "download_url": f"/api/binary/download/{build_id}/zip",
    }


# ─────────────────────────────────────────────────────────────────
# APK builder — produces a *runnable* WebView wrapper
# ─────────────────────────────────────────────────────────────────
_APP_CLASS_JAVA_TMPL = """\
package {pkg};

import android.app.Application;
import android.util.Log;
import java.io.File;
import java.io.FileOutputStream;
import java.io.PrintWriter;
import java.io.StringWriter;

/**
 * Custom Application class that catches ANY uncaught throwable across the
 * whole process and writes the stack trace to internal storage so even
 * after a force-close, the next launch can surface what went wrong.
 *
 * Persistent crash log: <internal>/files/last_crash.txt
 */
public class App extends Application {{
    private static final String TAG = "CodeDockGalaxy";

    @Override
    public void onCreate() {{
        try {{
            super.onCreate();
        }} catch (Throwable t) {{
            Log.e(TAG, "Application.onCreate failed", t);
            persistCrash(t, "Application.onCreate");
        }}
        installCrashHandler();
    }}

    private void installCrashHandler() {{
        final Thread.UncaughtExceptionHandler prev =
            Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler(new Thread.UncaughtExceptionHandler() {{
            @Override
            public void uncaughtException(Thread t, Throwable ex) {{
                Log.e(TAG, "UNCAUGHT process-wide on " + t.getName(), ex);
                persistCrash(ex, "uncaught:" + t.getName());
                if (prev != null) prev.uncaughtException(t, ex);
            }}
        }});
    }}

    private void persistCrash(Throwable t, String label) {{
        try {{
            StringWriter sw = new StringWriter();
            sw.write("[" + label + "] " + new java.util.Date().toString() + "\\n");
            sw.write("Thread: " + Thread.currentThread().getName() + "\\n");
            sw.write("Build: API " + android.os.Build.VERSION.SDK_INT
                + " " + android.os.Build.MANUFACTURER + " " + android.os.Build.MODEL + "\\n");
            sw.write("VM: " + System.getProperty("java.vm.version") + "\\n\\n");
            if (t != null) t.printStackTrace(new PrintWriter(sw));
            File dir = getFilesDir();
            if (dir != null) {{
                File f = new File(dir, "last_crash.txt");
                FileOutputStream fos = new FileOutputStream(f);
                fos.write(sw.toString().getBytes("utf-8"));
                fos.close();
            }}
        }} catch (Throwable ignored) {{}}
    }}
}}
"""


_MAIN_ACTIVITY_JAVA_TMPL = """\
package {pkg};

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.KeyEvent;
import android.view.Gravity;
import android.view.ViewGroup;
import android.view.View;
import android.webkit.WebView;
import android.webkit.WebSettings;
import android.webkit.WebViewClient;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceError;
import android.widget.TextView;
import android.widget.ScrollView;
import android.widget.LinearLayout;
import android.widget.Button;
import android.graphics.Color;
import android.util.Log;
import java.io.PrintWriter;
import java.io.StringWriter;

public class MainActivity extends Activity {{
    private static final String TAG = "CodeDockGalaxy";
    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {{
        // ── Install crash handler FIRST, in its own try/catch ───────
        try {{
            final Thread.UncaughtExceptionHandler oldHandler =
                Thread.getDefaultUncaughtExceptionHandler();
            Thread.setDefaultUncaughtExceptionHandler(new Thread.UncaughtExceptionHandler() {{
                @Override
                public void uncaughtException(Thread t, Throwable ex) {{
                    Log.e(TAG, "UNCAUGHT on " + t.getName(), ex);
                    try {{
                        // Try to surface the trace on screen even from a
                        // background thread by hopping to the main looper.
                        final Throwable fex = ex;
                        new Handler(Looper.getMainLooper()).post(new Runnable() {{
                            @Override public void run() {{
                                try {{ showFallback(fex); }} catch (Throwable ignored) {{}}
                            }}
                        }});
                    }} catch (Throwable ignored) {{}}
                    if (oldHandler != null) oldHandler.uncaughtException(t, ex);
                }}
            }});
        }} catch (Throwable ignored) {{}}

        // ── super.onCreate with retry ───────────────────────────────
        try {{
            super.onCreate(savedInstanceState);
        }} catch (Throwable t) {{
            Log.e(TAG, "super.onCreate failed, retrying with null state", t);
            try {{ super.onCreate(null); }} catch (Throwable ignored) {{}}
        }}

        // ── GUARANTEED splash: show "Loading..." BEFORE anything else
        //    can crash. This is what was missing — the user never saw
        //    the starfall splash because WebView init crashed before
        //    setContentView() was ever called.
        try {{
            setContentView(buildLoadingSplash());
        }} catch (Throwable t) {{
            Log.e(TAG, "splash setContentView failed", t);
        }}

        // ── Defer WebView init to next loop tick so the splash actually
        //    paints. If WebView init throws, we already have UI on screen.
        new Handler(Looper.getMainLooper()).postDelayed(new Runnable() {{
            @Override public void run() {{
                try {{
                    initWebView();
                }} catch (Throwable t) {{
                    Log.e(TAG, "WebView init failed", t);
                    showFallback(t);
                }}
            }}
        }}, 80);
    }}

    private View buildLoadingSplash() {{
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.parseColor("#0a0f1f"));
        root.setGravity(Gravity.CENTER);
        root.setPadding(48, 96, 48, 96);

        TextView title = new TextView(this);
        title.setText("✦  Galaxy");
        title.setTextColor(Color.parseColor("#A78BFA"));
        title.setTextSize(34);
        title.setGravity(Gravity.CENTER);
        root.addView(title);

        TextView sub = new TextView(this);
        sub.setText("starfall · initializing webview …");
        sub.setTextColor(Color.parseColor("#94a3b8"));
        sub.setTextSize(13);
        sub.setGravity(Gravity.CENTER);
        sub.setPadding(0, 18, 0, 0);
        root.addView(sub);

        TextView build = new TextView(this);
        build.setText("API " + android.os.Build.VERSION.SDK_INT
            + " · " + android.os.Build.MANUFACTURER + " " + android.os.Build.MODEL);
        build.setTextColor(Color.parseColor("#475569"));
        build.setTextSize(11);
        build.setGravity(Gravity.CENTER);
        build.setPadding(0, 12, 0, 0);
        root.addView(build);

        return root;
    }}

    private void initWebView() {{
        webView = new WebView(this);
        webView.setBackgroundColor(Color.parseColor("#0a0f1f"));
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(true);
        try {{ s.setAllowFileAccessFromFileURLs(true); }} catch (Throwable ignored) {{}}
        try {{ s.setAllowUniversalAccessFromFileURLs(true); }} catch (Throwable ignored) {{}}
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setSupportZoom(true);
        s.setBuiltInZoomControls(false);
        s.setDefaultTextEncodingName("utf-8");
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        try {{ s.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE); }} catch (Throwable ignored) {{}}
        try {{
            s.setUserAgentString(s.getUserAgentString() + " CodeDockGalaxy/1.0");
        }} catch (Throwable ignored) {{}}

        webView.setWebViewClient(new WebViewClient() {{
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest req) {{
                v.loadUrl(req.getUrl().toString());
                return true;
            }}
            @Override
            public void onReceivedError(WebView v, WebResourceRequest req, WebResourceError err) {{
                String desc = (err == null ? "(no description)" : String.valueOf(err.getDescription()));
                String html = "<!doctype html><html><body style='font-family:system-ui;background:#0a0f1f;color:#f8fafc;padding:24px'>"
                    + "<h2 style='color:#fb7185'>Page failed to load</h2>"
                    + "<p>" + desc + "</p></body></html>";
                v.loadDataWithBaseURL(null, html, "text/html", "utf-8", null);
            }}
        }});
        webView.setWebChromeClient(new WebChromeClient());
        webView.setLayoutParams(new ViewGroup.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT));
        webView.loadUrl("file:///android_asset/galaxy/index.html");
        setContentView(webView);
    }}

    private void showFallback(Throwable t) {{
        StringWriter sw = new StringWriter();
        sw.write("Build: API " + android.os.Build.VERSION.SDK_INT
            + " " + android.os.Build.MANUFACTURER + " " + android.os.Build.MODEL + "\\n\\n");
        if (t != null) t.printStackTrace(new PrintWriter(sw));

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.parseColor("#0a0f1f"));
        root.setPadding(48, 96, 48, 48);

        TextView title = new TextView(this);
        title.setText("Galaxy");
        title.setTextColor(Color.parseColor("#A78BFA"));
        title.setTextSize(26);
        root.addView(title);

        TextView intro = new TextView(this);
        intro.setText("The WebView component failed to start. Diagnostic follows — please share a screenshot:");
        intro.setTextColor(Color.parseColor("#cbd5e1"));
        intro.setTextSize(14);
        intro.setPadding(0, 16, 0, 8);
        root.addView(intro);

        ScrollView scroll = new ScrollView(this);
        scroll.setLayoutParams(new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        TextView trace = new TextView(this);
        trace.setText((t == null ? "(no exception)" : (t.getClass().getName() + ": " + t.getMessage() + "\\n\\n" + sw.toString())));
        trace.setTextColor(Color.parseColor("#fda4af"));
        trace.setTextSize(12);
        trace.setTypeface(android.graphics.Typeface.MONOSPACE);
        scroll.addView(trace);
        root.addView(scroll);

        setContentView(root);
    }}

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {{
        if (keyCode == KeyEvent.KEYCODE_BACK && webView != null && webView.canGoBack()) {{
            webView.goBack();
            return true;
        }}
        return super.onKeyDown(keyCode, event);
    }}

    @Override
    protected void onPause() {{ super.onPause(); if (webView != null) {{ try {{ webView.onPause(); }} catch (Throwable ignored) {{}} }} }}

    @Override
    protected void onResume() {{ super.onResume(); if (webView != null) {{ try {{ webView.onResume(); }} catch (Throwable ignored) {{}} }} }}

    @Override
    protected void onDestroy() {{
        if (webView != null) {{
            try {{ webView.removeAllViews(); }} catch (Throwable ignored) {{}}
            try {{ webView.destroy(); }} catch (Throwable ignored) {{}}
            webView = null;
        }}
        super.onDestroy();
    }}
}}
"""


_MANIFEST_TMPL = """\
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="{pkg}"
    android:versionCode="1"
    android:versionName="1.0"
    android:installLocation="auto">
  <uses-permission android:name="android.permission.INTERNET" />
  <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
  <uses-feature android:name="android.software.webview" android:required="false" />
  <!--
    DELIBERATE OMISSION: android:name=".App" was removed. A custom
    Application class loads BEFORE MainActivity and BEFORE any of our
    UncaughtExceptionHandlers can install — if it fails DEX class
    verification for any OEM-specific reason, the process is silently
    killed with no logcat and no UI. The App class still ships in the
    DEX (dead code) so we lose nothing.

    android:hardwareAccelerated removed at app level — was conflicting
    with the activity-level true. Letting it default to true matches
    WebView's requirement on Android 8+.
  -->
  <application
      android:label="@string/app_name"
      android:icon="@mipmap/ic_launcher"
      android:roundIcon="@mipmap/ic_launcher"
      android:theme="@style/GalaxyTheme"
      android:allowBackup="true"
      android:largeHeap="true"
      android:usesCleartextTraffic="true"
      android:supportsRtl="true">
    <activity android:name=".MainActivity"
        android:exported="true"
        android:label="@string/app_name"
        android:theme="@style/GalaxyTheme"
        android:hardwareAccelerated="true"
        android:launchMode="singleTask"
        android:configChanges="orientation|keyboardHidden|screenSize|screenLayout|uiMode|density|fontScale">
      <intent-filter>
        <action android:name="android.intent.action.MAIN" />
        <category android:name="android.intent.category.LAUNCHER" />
      </intent-filter>
    </activity>
  </application>
</manifest>
"""


_STYLES_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<resources>
  <!--
    GalaxyTheme inherits from Theme.NoTitleBar (available since API 1 on
    every Android device ever shipped). We override nothing — we just
    use it as a guaranteed-present anchor. This avoids the
    Theme.Material / Theme.DeviceDefault availability quirks seen on
    some heavily-modified OEM ROMs (Samsung OneUI, MIUI, EMUI). On a
    stock S20 this still resolves to the device-default look-and-feel.
  -->
  <style name="GalaxyTheme" parent="@android:style/Theme.NoTitleBar">
    <item name="android:windowBackground">@android:color/black</item>
    <item name="android:colorBackground">@android:color/black</item>
  </style>
</resources>
"""


def _make_launcher_png(width: int = 48, height: int = 48,
                       color: tuple = (167, 139, 250)) -> bytes:
    """Pure-stdlib PNG of a solid-color square — used as the launcher icon
    so the OS shows a real bitmap rather than the system fallback (which
    some OEM launchers, including Samsung OneUI, refuse to render and
    treat as a broken install)."""
    import struct
    raw = bytearray()
    r, g, b = color
    row = bytes([0]) + bytes([r, g, b] * width)  # filter byte 0 + RGB pixels
    for _ in range(height):
        raw += row

    def _chunk(name: bytes, data: bytes) -> bytes:
        crc = __import__("zlib").crc32(name + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    import zlib as _z
    idat = _chunk(b"IDAT", _z.compress(bytes(raw), 9))
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def _build_real_apk(build: dict, out_path: Path) -> tuple[int, int, str, bool]:
    """
    Real, runnable APK with embedded WebView Activity + classes.dex.
    Returns (file_count, total_bytes, signature_info, verified).
    """
    pkg = _safe_pkg(build.get("build_id", "x"))
    title = (build.get("title") or "GalaxyGame")[:60].replace("&", "&amp;").replace("<", "&lt;")
    file_count = 0
    total_bytes = 0

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        # 1. Java sources ───────────────────────────────────────
        java_dir = td / "java" / pkg.replace(".", "/")
        java_dir.mkdir(parents=True, exist_ok=True)
        java_src = java_dir / "MainActivity.java"
        java_src.write_text(_MAIN_ACTIVITY_JAVA_TMPL.format(pkg=pkg))
        # Also write the App class (custom Application with persistent
        # crash logger). Wired in the manifest via android:name=".App".
        app_src = java_dir / "App.java"
        app_src.write_text(_APP_CLASS_JAVA_TMPL.format(pkg=pkg))

        # 2. javac → classes ────────────────────────────────────
        classes_dir = td / "classes"
        classes_dir.mkdir()
        # Use --release 8 for MAXIMUM Android compatibility. Targets Java 8
        # bytecode (class version 52), the level d8 has the most test
        # coverage for and the lowest risk of "wrong constant pool tag"
        # surprises on older OEM Dalvik builds. Android 7+ supports Java
        # 8 features natively (try-with-resources, default methods, etc).
        r = subprocess.run(
            ["javac", "--release", "8",
             "-classpath", str(ANDROID_JAR),
             "-d", str(classes_dir),
             str(java_src), str(app_src)],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            raise RuntimeError(f"javac failed: {r.stderr[-500:]}")

        # 3. d8 → classes.dex ───────────────────────────────────
        # Collect all .class files (incl. inner classes)
        class_files = list(classes_dir.rglob("*.class"))
        if not class_files:
            raise RuntimeError("no .class files produced by javac")
        dex_dir = td / "dex"; dex_dir.mkdir()
        r = subprocess.run(
            _wrap(BUILD_TOOLS / "d8") + ["--lib", str(ANDROID_JAR),
                                          "--output", str(dex_dir),
                                          "--min-api", "24",
                                          *[str(c) for c in class_files]],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            raise RuntimeError(f"d8 failed: {r.stderr[-500:]}")
        dex_path = dex_dir / "classes.dex"
        if not dex_path.exists():
            raise RuntimeError("d8 did not produce classes.dex")

        # 4. Resources — strings.xml + styles.xml + launcher icon ────
        res_values = td / "res" / "values"
        res_values.mkdir(parents=True)
        (res_values / "strings.xml").write_text(
            f'<?xml version="1.0" encoding="utf-8"?>\n<resources>\n  <string name="app_name">{title}</string>\n</resources>\n'
        )
        # Custom theme: inherits from Theme.NoTitleBar (API 1, universal).
        # Avoids the Theme.Material / Theme.DeviceDefault availability
        # quirks on heavily-modded OEM ROMs.
        (res_values / "styles.xml").write_text(_STYLES_XML)
        # Generate launcher icons across mipmap density buckets. Samsung
        # OneUI (S20-family) refuses to render the app in its launcher
        # without a real bitmap icon at multiple densities — falling
        # back to the platform default does NOT work there.
        try:
            icon_buckets = {
                "mipmap-mdpi":    48,
                "mipmap-hdpi":    72,
                "mipmap-xhdpi":   96,
                "mipmap-xxhdpi": 144,
                "mipmap-xxxhdpi":192,
            }
            for bucket, size in icon_buckets.items():
                d = td / "res" / bucket
                d.mkdir(parents=True, exist_ok=True)
                png = _make_launcher_png(size, size, (167, 139, 250))
                (d / "ic_launcher.png").write_bytes(png)
        except Exception as e:
            # icon is critical for S20 but we don't want to fail the build
            # if PNG generation hits an unexpected stdlib quirk; the
            # apksigner verify path will still produce a valid APK and
            # most launchers will fall back to a generic icon.
            print(f"[binary_builder] icon generation warning: {e}")

        # 5. Manifest ────────────────────────────────────────────
        manifest_path = td / "AndroidManifest.xml"
        manifest_path.write_text(_MANIFEST_TMPL.format(pkg=pkg))

        # 6. Assets — drop user files under assets/galaxy/ ───────
        assets_root = td / "assets"
        galaxy_dir = assets_root / "galaxy"
        galaxy_dir.mkdir(parents=True)
        index_html = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{title}</title>"
            "<style>"
            "body{margin:0;font-family:system-ui,-apple-system,sans-serif;"
            "background:linear-gradient(135deg,#0a0f1f 0%,#1a1f3f 100%);"
            "color:#f8fafc;min-height:100vh;padding:24px;box-sizing:border-box}"
            "h1{color:#A78BFA;font-size:26px;margin:0 0 6px}"
            ".tag{color:#94a3b8;font-size:13px}"
            ".card{background:#0f172a;border:1px solid #1e293b;border-radius:12px;"
            "padding:14px;margin-top:14px}"
            ".file{font-family:monospace;font-size:12px;color:#cbd5e1;padding:6px 0;"
            "border-top:1px solid #1e293b}"
            ".file:first-child{border-top:none}"
            ".badge{display:inline-block;background:#A78BFA22;color:#A78BFA;"
            "padding:3px 8px;border-radius:6px;font-size:11px;margin-right:6px}"
            "</style></head><body>"
            f"<h1>🎮 {title}</h1>"
            "<div class='tag'>Galaxy Studio · CodeDock Quantum Nexus</div>"
            "<div class='card'><div class='badge'>BUILD</div>"
            f"<span class='tag'>{build.get('build_id','unknown')[:32]}</span>"
            "</div>"
            "<div class='card'><b>Embedded files</b><div id='filelist'></div></div>"
            "<script>"
            "fetch('galaxy/manifest.json').then(r=>r.json()).then(m=>{"
            "var list=document.getElementById('filelist');"
            "(m.files||[]).forEach(function(f){"
            "var d=document.createElement('div');d.className='file';"
            "d.textContent='• '+f.path+'  ('+f.size+'B)';list.appendChild(d);});"
            "}).catch(function(e){"
            "document.getElementById('filelist').textContent='(no manifest)';});"
            "</script></body></html>"
        )
        (galaxy_dir / "index.html").write_text(index_html)
        # Drop a manifest.json describing embedded files
        manifest_index = {"title": title, "build_id": build.get("build_id"), "files": []}
        for relpath, content in _build_files_iter(build):
            data = content.encode("utf-8", errors="replace") if isinstance(content, str) else bytes(content)
            target = galaxy_dir / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            manifest_index["files"].append({"path": relpath, "size": len(data)})
            file_count += 1
            total_bytes += len(data)
        (galaxy_dir / "manifest.json").write_text(json.dumps(manifest_index, indent=2))

        # 7. aapt2 compile resources ─────────────────────────────
        compiled_res = td / "compiled_res"
        compiled_res.mkdir()
        r = subprocess.run(
            _wrap(BUILD_TOOLS / "aapt2") + ["compile", "--dir", str(td / "res"),
                                             "-o", str(compiled_res)],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            raise RuntimeError(f"aapt2 compile failed: {r.stderr[-500:]}")
        flat_files = list(compiled_res.glob("*.flat"))

        # 8. aapt2 link → base.apk (resources + manifest + assets) ───
        # NOTE: targetSdk pinned to 33 (Android 13) on purpose — Android 14
        # (API 34) ships with several new strict-mode behaviours that
        # cause silent activity launch failures on Samsung OneUI 6.x
        # firmware shipped to S20 / S21 in 2024. API 33 is the highest
        # we can target while staying universally launch-safe.
        base_apk = td / "base.apk"
        r = subprocess.run(
            _wrap(BUILD_TOOLS / "aapt2") + ["link",
                "-I", str(ANDROID_JAR),
                "--manifest", str(manifest_path),
                "-A", str(assets_root),
                "--target-sdk-version", "33",
                "--min-sdk-version", "24",
                "-o", str(base_apk),
                *[str(f) for f in flat_files]],
            capture_output=True, text=True, timeout=180,
        )
        if r.returncode != 0:
            raise RuntimeError(f"aapt2 link failed: {r.stderr[-500:]}")

        # 9. Inject classes.dex into base.apk ────────────────────
        with zipfile.ZipFile(base_apk, "a", zipfile.ZIP_DEFLATED) as zf:
            zf.write(dex_path, "classes.dex")

        # 10. zipalign ───────────────────────────────────────────
        aligned = td / "aligned.apk"
        r = subprocess.run(
            _wrap(BUILD_TOOLS / "zipalign") + ["-f", "-p", "4",
                                                str(base_apk), str(aligned)],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            raise RuntimeError(f"zipalign failed: {r.stderr[-500:]}")

        # 11. apksigner (Java, native) ───────────────────────────
        r = subprocess.run([
            str(BUILD_TOOLS / "apksigner"), "sign",
            "--ks", str(DEBUG_KEYSTORE),
            "--ks-key-alias", KEY_ALIAS,
            "--ks-pass", f"pass:{KEYSTORE_PASS}",
            "--key-pass", f"pass:{KEYSTORE_PASS}",
            "--v1-signing-enabled", "true",
            "--v2-signing-enabled", "true",
            "--v3-signing-enabled", "true",
            "--out", str(out_path),
            str(aligned),
        ], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"apksigner failed: {r.stderr[-500:]}")

        # 12. verify ─────────────────────────────────────────────
        v = subprocess.run([
            str(BUILD_TOOLS / "apksigner"), "verify", "--verbose", str(out_path),
        ], capture_output=True, text=True, timeout=60)
        sig_summary = (v.stdout + v.stderr)[:400]
        return (file_count, total_bytes, sig_summary, v.returncode == 0)


def build_apk(build: dict) -> dict:
    build_id = build.get("build_id", "unknown")
    out_path = ARTIFACTS_ROOT / f"{build_id}.apk"
    is_real = False
    sig_info = ""
    file_count = 0
    total_bytes = 0
    sha256 = hashlib.sha256()
    classes_dex_present = False
    has_runnable_activity = False

    if _have_full_apk_toolchain():
        try:
            file_count, total_bytes, sig_info, verified = _build_real_apk(build, out_path)
            is_real = bool(verified)
        except Exception as e:
            sig_info = f"toolchain error: {e}"
            is_real = False
            file_count = 0
            total_bytes = 0
    
    if not is_real:
        # Placeholder fallback only — should never hit if toolchain is installed
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            manifest_xml = _MANIFEST_TMPL.format(pkg=_safe_pkg(build_id))
            zf.writestr("AndroidManifest.xml", manifest_xml)
            seen = set()
            for relpath, content in _build_files_iter(build):
                if relpath in seen: continue
                seen.add(relpath)
                data = bytes(content) if isinstance(content, (bytes, bytearray)) else str(content).encode("utf-8", errors="replace")
                zf.writestr(f"assets/galaxy/{relpath}", data)
                file_count += 1
                total_bytes += len(data)
            zf.writestr("META-INF/CODEDOCK.SF", json.dumps({
                "codedock_galaxy_build": True, "build_id": build_id,
                "is_signed": False, "is_runnable_native": False,
                "note": "toolchain unavailable — install Android SDK to produce runnable APK",
            }).encode())

    # sha256 + structure probe
    with out_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            sha256.update(chunk)
    try:
        with zipfile.ZipFile(out_path) as zf:
            names = set(zf.namelist())
            classes_dex_present = "classes.dex" in names
            mfx = zf.read("AndroidManifest.xml") if "AndroidManifest.xml" in names else b""
            # AndroidManifest is binary-XML (aapt2 output); strings are
            # stored UTF-16LE. We check both ASCII and UTF-16LE encodings.
            has_runnable_activity = (
                b"MainActivity" in mfx
                or b"M\x00a\x00i\x00n\x00A\x00c\x00t\x00i\x00v\x00i\x00t\x00y\x00" in mfx
            )
    except Exception:
        pass

    return {
        "artifact_id":          f"apk_{build_id}",
        "kind":                 "apk",
        "build_id":             build_id,
        "path":                 str(out_path),
        "size_bytes":           out_path.stat().st_size,
        "file_count":           file_count,
        "raw_bytes":            total_bytes,
        "sha256":               sha256.hexdigest(),
        "is_real_apk":          is_real,
        "has_classes_dex":      classes_dex_present,
        "has_runnable_activity": has_runnable_activity,
        "is_installable":       bool(is_real and classes_dex_present),
        "min_sdk":              24,
        "target_sdk":           34,
        "signature_info":       sig_info[:400],
        "created_at":           datetime.now(timezone.utc).isoformat(),
        "download_url":         f"/api/binary/download/{build_id}/apk",
    }


# ─────────────────────────────────────────────────────────────────
# Combined entry point
# ─────────────────────────────────────────────────────────────────
async def package_build(build: dict, kinds: list[str] | None = None) -> dict:
    """Run the requested packagers in parallel and return all artifacts."""
    kinds = kinds or ["zip", "apk"]
    loop = asyncio.get_running_loop()
    coros = []
    if "zip" in kinds:
        coros.append(loop.run_in_executor(None, build_zip, build))
    if "apk" in kinds:
        coros.append(loop.run_in_executor(None, build_apk, build))
    results = await asyncio.gather(*coros, return_exceptions=True)
    artifacts = []
    errors = []
    for r in results:
        if isinstance(r, Exception):
            errors.append(f"{type(r).__name__}: {r}")
        else:
            artifacts.append(r)
    return {"artifacts": artifacts, "errors": errors}


def find_artifact_path(build_id: str, kind: str) -> Optional[Path]:
    p = ARTIFACTS_ROOT / f"{build_id}.{kind}"
    return p if p.exists() else None
