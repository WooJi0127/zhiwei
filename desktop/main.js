/**
 * 知未 · 桌面端主进程（Electron）
 *
 * 设计要点：
 *  1. 前端资源始终用安装包内置的 app/，随软件升级一起更新
 *  2. 数据文件可以单独热更新——下载新的 data.js 存到用户目录，
 *     再用 webRequest 把对 app 目录下 data.js 的请求重定向过去。
 *     这样用户不用重装软件也能拿到最新的回归数据。
 *     注意：注释里千万别照抄下面 webRequest 那个 URL 模式，
 *     它里面带「星号紧跟斜杠」，会把这段块注释提前结束掉。
 *  3. 纯本地应用，禁止在应用内乱跳外部网址
 */
const { app, BrowserWindow, Menu, dialog, shell, session } = require("electron");
const path = require("path");
const fs = require("fs");
const https = require("https");
const http = require("http");

// 数据热更新的来源。想换成自己的站点，改这里就行。
const UPDATE_URL =
  process.env.ZHIWEI_UPDATE_URL ||
  "https://zhiwei-kpop.pages.dev/app/data/data.js";

const APP_NAME = "知未";

let mainWindow = null;
let cachedDataPath = null;   // 用户目录里已缓存的 data.js

/** 用户数据目录：%APPDATA%/知未 */
function userDir() {
  const d = path.join(app.getPath("userData"));
  if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true });
  return d;
}

/** 从 data.js 里抠出 generated 字段（文件 1MB+，别整个解析） */
function readGenerated(file) {
  try {
    const head = fs.readFileSync(file, "utf8").slice(0, 4000);
    const m = head.match(/generated\s*:\s*"([^"]+)"/);
    return m ? m[1] : "";
  } catch (e) {
    return "";
  }
}

function builtinData() {
  return path.join(__dirname, "app", "data", "data.js");
}

function currentData() {
  return cachedDataPath && fs.existsSync(cachedDataPath)
    ? cachedDataPath
    : builtinData();
}

/**
 * 把对 data/data.js 的请求重定向到用户目录的缓存（有更新的话）。
 * 注意：别把下面 webRequest 的 URL 模式照抄进注释，
 * 它含「星号紧跟斜杠」，会把块注释提前结束掉。
 */
function installDataRedirect() {
  session.defaultSession.webRequest.onBeforeRequest(
    { urls: ["file://*/data/data.js*", "file://*/data\\data.js*"] },
    (details, callback) => {
      if (cachedDataPath && fs.existsSync(cachedDataPath)) {
        callback({ redirectURL: "file:///" + cachedDataPath.replace(/\\/g, "/") });
      } else {
        callback({});
      }
    }
  );
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1240,
    height: 860,
    minWidth: 960,
    minHeight: 640,
    title: APP_NAME + " · K-POP 回归日历",
    backgroundColor: "#f2f3f9",
    autoHideMenuBar: false,
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, "app", "index.html"));

  if (process.env.ZHIWEI_SMOKE) {
    // 自检钩子：ZHIWEI_SMOKE=<截图路径> 时，页面加载完自动截图并退出。
    // 打包机 / 无显卡的命令行环境下用它确认界面真的渲染出来了。
    // 挂在 did-finish-load 上而非 ready-to-show——后者在 GPU 异常时可能永不触发。
    mainWindow.webContents.once("did-finish-load", () => {
      setTimeout(() => {
        mainWindow.webContents.capturePage()
          .then((img) => fs.writeFileSync(process.env.ZHIWEI_SMOKE, img.toPNG()))
          .catch(() => {})
          .finally(() => app.exit(0));      // 强制退出，不等窗口关闭
      }, 1200);
    });
  }

  mainWindow.once("ready-to-show", () => mainWindow.show());

  // 外链一律交给系统浏览器，不在应用里开新窗口
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url && /^https?:/i.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  mainWindow.webContents.on("will-navigate", (e, url) => {
    if (!url.startsWith("file://")) {
      e.preventDefault();
      if (/^https?:/i.test(url)) shell.openExternal(url);
    }
  });

  mainWindow.on("closed", () => { mainWindow = null; });
}

// ------------------------------------------------------------ 数据更新
function download(url, redirect = 0) {
  return new Promise((resolve, reject) => {
    const mod = url.startsWith("http:") ? http : https;
    const req = mod.get(url, { timeout: 20000 }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        if (redirect > 3) return reject(new Error("重定向次数过多"));
        return download(new URL(res.headers.location, url).href, redirect + 1)
          .then(resolve, reject);
      }
      if (res.statusCode !== 200) {
        res.resume();
        return reject(new Error("HTTP " + res.statusCode));
      }
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => resolve(Buffer.concat(chunks)));
    });
    req.on("timeout", () => { req.destroy(new Error("请求超时")); });
    req.on("error", reject);
  });
}

async function checkUpdate(silent = false) {
  try {
    const buf = await download(UPDATE_URL);
    const text = buf.toString("utf8");
    if (!text.includes("__KPOP_DATA__")) throw new Error("返回的内容不是数据文件");

    const m = text.match(/generated\s*:\s*"([^"]+)"/);
    const remote = m ? m[1] : "";
    const local = readGenerated(currentData());

    if (remote && remote === local) {
      if (!silent) {
        dialog.showMessageBox(mainWindow, {
          type: "info",
          title: "数据已是最新",
          message: "当前数据已经是最新版本",
          detail: "数据生成时间：" + (local || "未知"),
          buttons: ["好"],
        });
      }
      return { updated: false, generated: local };
    }

    const dest = path.join(userDir(), "data.js");
    fs.writeFileSync(dest, buf);
    cachedDataPath = dest;

    if (!silent) {
      const r = await dialog.showMessageBox(mainWindow, {
        type: "info",
        title: "数据已更新",
        message: "已获取最新数据，需要重启应用生效",
        detail: `${local || "未知"}  →  ${remote || "最新"}`,
        buttons: ["立即重启", "稍后"],
        defaultId: 0,
      });
      if (r.response === 0) {
        app.relaunch();
        app.exit(0);
      }
    }
    return { updated: true, generated: remote };
  } catch (err) {
    if (!silent) {
      dialog.showMessageBox(mainWindow, {
        type: "warning",
        title: "更新失败",
        message: "没能获取到新数据",
        detail: err.message + "\n\n可以稍后再试，当前仍在使用上一次的数据。",
        buttons: ["好"],
      });
    }
    return { updated: false, error: err.message };
  }
}

// ------------------------------------------------------------ 菜单
function buildMenu() {
  const isMac = process.platform === "darwin";
  const template = [
    {
      label: "文件",
      submenu: [
        {
          label: "检查数据更新…",
          accelerator: "CmdOrCtrl+U",
          click: () => checkUpdate(false),
        },
        { type: "separator" },
        { label: "退出", role: isMac ? "close" : "quit", accelerator: "CmdOrCtrl+Q" },
      ],
    },
    {
      label: "查看",
      submenu: [
        { label: "重新加载", role: "reload", accelerator: "CmdOrCtrl+R" },
        { label: "实际大小", role: "resetZoom", accelerator: "CmdOrCtrl+0" },
        { label: "放大", role: "zoomIn", accelerator: "CmdOrCtrl+=" },
        { label: "缩小", role: "zoomOut", accelerator: "CmdOrCtrl+-" },
        { type: "separator" },
        { label: "全屏", role: "togglefullscreen", accelerator: "F11" },
        { type: "separator" },
        { label: "开发者工具", role: "toggleDevTools", accelerator: "F12" },
      ],
    },
    {
      label: "帮助",
      submenu: [
        {
          label: "关于 " + APP_NAME,
          click: () => {
            const g = readGenerated(currentData());
            dialog.showMessageBox(mainWindow, {
              type: "info",
              title: "关于 " + APP_NAME,
              message: APP_NAME + " · K-POP 回归日历",
              detail: [
                "版本 " + app.getVersion(),
                "数据生成时间：" + (g || "未知"),
                "",
                "数据来源：kpopping.com / Apple Music / 网易云音乐 / kpopcal.com",
                "「知未」仅做信息聚合，不提供播放服务。",
              ].join("\n"),
              buttons: ["好"],
            });
          },
        },
        {
          label: "访问官网",
          click: () => shell.openExternal("https://zhiwei-kpop.pages.dev"),
        },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// ------------------------------------------------------------ 启动
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(() => {
    const p = path.join(userDir(), "data.js");
    if (fs.existsSync(p)) cachedDataPath = p;
    installDataRedirect();
    buildMenu();
    createWindow();

    // 每次启动 quietly 检查一次，有新数据就在标题栏提示
    checkUpdate(true).then((r) => {
      if (r.updated && mainWindow) {
        mainWindow.setTitle(APP_NAME + " · 有新数据，重启后生效");
      }
    });

    app.on("activate", () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });
}

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
