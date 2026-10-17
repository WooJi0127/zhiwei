# 在 Mac 上构建 iOS 版「知未」

iOS 应用只能在 macOS + Xcode 上编译，所以这一步没法在 Windows 上完成。
好消息是**工程已经配好了**——`mobile/ios/App/App.xcodeproj` 已生成，
应用名、Bundle ID、图标、方向锁定、浅色模式都已设置，你在 Mac 上只需要打开、签名、运行。

---

## 一、准备

| 需要 | 说明 |
|---|---|
| macOS | 12 以上（Xcode 15 要求） |
| Xcode | App Store 搜 Xcode，约 10 GB |
| CocoaPods | 终端执行 `sudo gem install cocoapods` |
| Node.js | 18+，用来跑 `cap sync` |
| Apple ID | 免费即可真机调试；上架 App Store 需付费开发者账号（¥688/年） |

第一次装完 Xcode 后，执行一次：

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept
```

---

## 二、构建步骤

把整个 `KPOP` 项目目录拷到 Mac（U 盘 / 网盘 / git 都行），然后：

```bash
cd KPOP/mobile

# 1. 装依赖（只第一次需要）
npm install

# 2. 把最新的网页资源同步进 iOS 工程，并安装原生依赖
npx cap sync ios
```

> `cap sync ios` 会自动生成 `Podfile` 并执行 `pod install`。
> 如果它报 CocoaPods 相关错误，进入 `ios/App` 手动跑一次 `pod install`。

```bash
# 3. 用 Xcode 打开工程
npx cap open ios
```

Xcode 打开后，按下面的「三、签名」配好，选中你的 iPhone 或模拟器，点 ▶ 运行。

---

## 三、签名（必做，否则装不上手机）

1. 左侧点最顶上的 **App** 工程 → **TARGETS: App** → **Signing & Capabilities**
2. 勾选 **Automatically manage signing**
3. **Team** 选你的 Apple ID
   （没有的话：Xcode → Settings → Accounts → 左下角 + → Add Apple ID）
4. 如果 Bundle Identifier `com.zhiwei.kpop` 已被占用，
   改成 `com.你的名字.kpop` —— 改完记得同步改 `capacitor.config.json` 里的 `appId`

> **免费账号的限制**：用免费 Apple ID 签的应用 7 天后会过期，需要重新连电脑安装一次。
> 想长期使用就买开发者账号，或者上 TestFlight。

---

## 四、发布到 App Store

1. Xcode 菜单 **Product → Archive**（先在上方设备栏选 *Any iOS Device (arm64)*）
2. 弹出的 Organizer 里点 **Distribute App → App Store Connect → Upload**
3. 登录 [App Store Connect](https://appstoreconnect.apple.com) 创建应用，填写：
   - 名称：知未
   - 副标题：K-POP 回归日历
   - 类别：音乐 / 参考
   - 截图：用 iPhone 15 Pro Max 和 6.7 寸各截几张
4. 在「App 隐私」里声明**不收集任何数据**（这个应用确实不收集）
5. 提交审核

审核通常 1–3 天。常见被拒原因及对策：

| 被拒理由 | 对策 |
|---|---|
| 4.3 内容重复 / 太简单 | 强调这是信息聚合工具，附上详细的回归日程、历史归档、曲目数据说明 |
| 5.1.1 隐私 | 明确说明无账号、无埋点、数据全在本地 |
| 版权（专辑封面） | 封面来自 Apple Music 的公开接口，属于合理引用；如被质疑可改为纯文字卡片 |

---

## 五、改完之后怎么更新

网页部分（界面、逻辑）的改动**不需要重新配置 iOS 工程**，只要：

```bash
cd KPOP
python tools/sync.py          # 或双击 build.bat
cd mobile && npx cap sync ios
```

然后回 Xcode 重新 Run / Archive 即可。

原生配置（图标、Info.plist、权限）的改动才需要在 Xcode 里操作。

---

## 六、这个工程里已经配好的东西

| 项目 | 值 | 在哪改 |
|---|---|---|
| 应用显示名 | 知未 | `App/App/Info.plist` → `CFBundleDisplayName` |
| Bundle ID | com.zhiwei.kpop | Xcode → Signing，或 `capacitor.config.json` → `appId` |
| 版本号 | 1.0.0 (build 1) | Xcode → General，或 `project.pbxproj` 的 `MARKETING_VERSION` |
| 图标 | 倒转时钟 | `App/App/Assets.xcassets/AppIcon.appiconset/` |
| 方向 | 竖屏 + 横屏（iPad 四向） | `Info.plist` → `UISupportedInterfaceOrientations` |
| 外观 | 锁定浅色（应用只有浅色主题） | `Info.plist` → `UIUserInterfaceStyle` |
| 状态栏 | 深色文字（配浅色背景） | `Info.plist` → `UIStatusBarStyle` |
| 加密声明 | 未使用加密（免每版审核问答） | `Info.plist` → `ITSAppUsesNonExemptEncryption` |
| 安全区适配 | 已处理刘海与底部横条 | `core/app.css` 的 `env(safe-area-inset-*)` |

---

## 七、不装 Xcode 也能用 iOS 版

如果只是想先在 iPhone 上用：

1. Safari 打开在线版：`https://你的域名/app/`
2. 点底部分享按钮 → **添加到主屏幕**

效果接近原生：全屏、有图标、无地址栏。缺点是数据不会自动更新（每次要看最新就用在线版）。
