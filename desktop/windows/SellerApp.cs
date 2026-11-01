using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

[assembly: System.Reflection.AssemblyTitle("Atelier Seller")]
[assembly: System.Reflection.AssemblyVersion("1.4.0.0")]

namespace AtelierSeller
{
    internal static class Program
    {
        [STAThread]
        private static void Main(string[] args)
        {
            System.Threading.Thread.CurrentThread.CurrentUICulture = System.Globalization.CultureInfo.GetCultureInfo("en-US");
            System.Threading.Thread.CurrentThread.CurrentCulture = System.Globalization.CultureInfo.GetCultureInfo("en-US");
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
            Application.ThreadException += delegate(object sender, System.Threading.ThreadExceptionEventArgs e) {
                MessageBox.Show("The app encountered a problem. Please reopen it. Your shop records remain on the server.\n" + e.Exception.GetType().Name,
                    "Atelier Seller", MessageBoxButtons.OK, MessageBoxIcon.Error);
            };
            Application.Run(new SellerWindow(args));
        }
    }

    public sealed class ConnectionPolicy
    {
        public static bool IsAllowedOrigin(string value)
        {
            Uri uri;
            return Uri.TryCreate(value, UriKind.Absolute, out uri)
                && String.IsNullOrEmpty(uri.UserInfo) && String.IsNullOrEmpty(uri.Query)
                && String.IsNullOrEmpty(uri.Fragment) && uri.AbsolutePath == "/"
                && (uri.Scheme == "https" || (uri.Scheme == "http" &&
                    (uri.Host == "127.0.0.1" || uri.Host == "localhost" || uri.Host == "[::1]")));
        }

        public static bool SameOrigin(Uri origin, string value)
        {
            Uri uri;
            return Uri.TryCreate(value, UriKind.Absolute, out uri)
                && String.IsNullOrEmpty(uri.UserInfo) && uri.Scheme == origin.Scheme
                && uri.Host == origin.Host && uri.Port == origin.Port;
        }

        public static string ProfileName(Uri origin)
        {
            using (var sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(origin.GetLeftPart(UriPartial.Authority))))
                    .Replace("-", "").Substring(0, 20);
        }
    }

    public sealed class ConnectionSettings
    {
        public readonly string Origin;
        public readonly bool IsDemo;
        public readonly bool IsSharedDemo;
        public string StartPath { get { return IsDemo ? "/" : "/seller/ai/"; } }

        public ConnectionSettings(string origin, string mode)
        {
            if (!ConnectionPolicy.IsAllowedOrigin(origin))
                throw new ArgumentException("Configure a valid HTTPS website origin (or local development address).");
            if (mode != "demo" && mode != "live" && mode != "shared-demo")
                throw new ArgumentException("Connection mode must be demo, live or shared-demo.");
            Origin = origin.TrimEnd('/');
            IsDemo = mode == "demo";
            IsSharedDemo = mode == "shared-demo";
        }

        public static ConnectionSettings FromValues(IDictionary<string, string> values)
        {
            string origin = "https://demo.maijiax.cn", mode = "demo";
            if (values.ContainsKey("origin")) origin = values["origin"];
            else if (values.ContainsKey("demoOrigin")) origin = values["demoOrigin"];
            if (values.ContainsKey("mode")) mode = values["mode"];
            return new ConnectionSettings(origin, mode);
        }
    }

    public static class SellerLocale
    {
        public static string Normalize(string code) { return (code ?? "").StartsWith("zh", StringComparison.OrdinalIgnoreCase) ? "zh-hans" : "en"; }
        private static readonly IDictionary<string, string> Chinese = new Dictionary<string, string> {
            {"Atelier Seller", "Atelier 卖家助手"}, {"Atelier Seller - School demo", "Atelier 卖家助手 - 课程演示"},
            {"Atelier Seller - Main website", "Atelier 卖家助手 - 主站"}, {"Products · Orders · AI", "商品 · 订单 · 智能助手"},
            {"AI assistant", "智能助手"}, {"Products", "商品"}, {"Orders", "订单"}, {"Open in browser", "在浏览器中打开"},
            {"Main website", "主站"}, {"Help", "帮助"}, {"Refresh", "刷新"}, {"Reconnect", "重新连接"},
            {"New demo", "新建演示"}, {"Demo", "演示"}, {"School demo", "课程演示"},
            {"Connecting to your seller workspace...", "正在连接卖家工作区…"},
            {"Shared school demo · No login · Products sync to the main website", "课程共享演示 · 无需登录 · 商品与主站同步"},
            {"Demo data · Payment and shipping are simulated", "演示数据 · 付款和发货均为模拟"},
            {"Navigation to another website was blocked. Use your browser to view external links.", "请在浏览器中打开外部链接。"},
            {"To download a file, choose Open in browser.", "下载文件时，请选择“在浏览器中打开”。"},
            {"Cannot connect to the seller service", "无法连接卖家服务"}, {"The page stopped responding", "页面停止响应"},
            {"Choose Refresh to reconnect. Your server records are unaffected.", "请选择“刷新”重新连接，服务器中的记录已保留。"},
            {"Microsoft Edge WebView2 is required", "需要 Microsoft Edge WebView2"}, {"The app could not start", "应用无法启动"},
            {"Start a new demo shop? Your current sample records will stay on the server.", "要新建演示店铺吗？现有演示记录仍会保留在服务器中。"}
        };
        public static string Text(string english, string language) {
            string translated;
            return Normalize(language) == "zh-hans" && Chinese.TryGetValue(english, out translated) ? translated : english;
        }
    }

    internal sealed class SellerWindow : Form
    {
        private readonly Color green = Color.FromArgb(37, 79, 62);
        private readonly Panel surface = new Panel { Dock = DockStyle.Fill, BackColor = Color.White };
        private readonly Label status = new Label { Dock = DockStyle.Bottom, Height = 30, TextAlign = ContentAlignment.MiddleLeft };
        private readonly ConnectionSettings connection;
        private WebView2 browser;
        private Uri origin;
        private bool switching;
        private string overrideOrigin;
        private string language = "en";
        private bool hasLanguagePreference;
        private bool settingLanguage;
        private readonly ComboBox languagePicker = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Width = 160 };
        private readonly Dictionary<Control, string> originalLabels = new Dictionary<Control, string>();
        private string LanguagePath { get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AtelierSeller", "language.txt"); } }
        private string T(string value) { return SellerLocale.Text(value, language); }

        public SellerWindow(string[] args)
        {
            Text = "Atelier Seller";
            MinimumSize = new Size(920, 680);
            Size = new Size(1320, 900);
            StartPosition = FormStartPosition.CenterScreen;
            Font = new Font("Segoe UI", 9F);
            BackColor = Color.FromArgb(243, 246, 242);
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }
            connection = LoadConnection();
            try { if (File.Exists(LanguagePath)) { language = SellerLocale.Normalize(File.ReadAllText(LanguagePath)); hasLanguagePreference = true; } } catch { }
            if (!connection.IsDemo) Text = connection.IsSharedDemo ? "Atelier Seller - School demo" : "Atelier Seller - Main website";
            for (int i = 0; i + 1 < args.Length; i++)
                if (args[i] == "--url" && ConnectionPolicy.IsAllowedOrigin(args[i + 1])) overrideOrigin = args[i + 1];

            var nav = new FlowLayoutPanel { Dock = DockStyle.Left, Width = 190, FlowDirection = FlowDirection.TopDown,
                WrapContents = false, Padding = new Padding(15, 25, 10, 12), BackColor = green };
            nav.Controls.Add(new Label { Text = "Atelier Seller", ForeColor = Color.White, Font = new Font(Font.FontFamily, 14F, FontStyle.Bold),
                Size = new Size(165, 34) });
            nav.Controls.Add(new Label { Text = "Products · Orders · AI", ForeColor = Color.FromArgb(207, 224, 212), Size = new Size(165, 44) });
            AddNav(nav, "AI assistant", "/seller/ai/");
            AddNav(nav, "Products", "/seller/products/");
            AddNav(nav, "Orders", "/seller/ai/?view=orders");
            var web = NavButton("Open in browser");
            web.Click += delegate { if (origin != null) OpenExternal(browser != null && browser.Source != null ? browser.Source.ToString() : origin.ToString()); };
            nav.Controls.Add(web);
            if (connection.IsDemo) {
                var clear = NavButton("New demo");
                clear.Click += delegate { NewDemo(); };
                nav.Controls.Add(clear);
            } else {
                var website = NavButton("Main website");
                website.Click += delegate { OpenExternal(connection.Origin + "/"); };
                nav.Controls.Add(website);
            }
            var about = NavButton("Help");
            about.Click += delegate {
                MessageBox.Show(language == "zh-hans"
                    ? "可以查询商品和订单，用自然语言提出库存、价格或新商品需求。修改会先生成预览，确认后才写入主站。\n\n课程演示无需卖家登录。发布商品后，其他人可在主站查看。\n\n语言选择会同时应用到菜单、工作区和智能助手回复。"
                    : connection.IsDemo
                    ? "This coursework demo uses sample products and orders. No account is required.\n\nThe website and Windows app use the same demo service. Each browser session has its own sample shop.\n\nDeepSeek interprets natural-language requests. Review and confirm each proposed change before it is saved to the demo database.\n\nPayments and shipments are simulated. Nothing is charged and no parcel is sent.\n\nTry My products, New listing, and My orders. Internet access and the demo server are required."
                    : connection.IsSharedDemo
                    ? "Shared school demo at " + connection.Origin + ".\n\nNo sign-in or seller verification is required. Everyone uses the existing main website catalogue.\n\nConfirm a new product draft, then publish it in the product editor. Published products are visible to teammates on the main website.\n\nUse test data only. API keys and database credentials are never stored in this app."
                    : "Connected to " + connection.Origin + ".\n\nSign in using your main website seller account. Products, orders and confirmed AI changes use that website's database and your existing shop permissions.\n\nNew products are saved as unpublished drafts after you confirm the preview. Add photos and publish in the product editor to make them visible to buyers.\n\nYour earlier demo products remain in the separate demo service. This app does not copy them into your main shop. API keys and database credentials are never stored in this app.",
                    T("Help"), MessageBoxButtons.OK, MessageBoxIcon.Information);
            };
            nav.Controls.Add(about);
            languagePicker.Items.AddRange(new object[] { "English", "中文" });
            languagePicker.SelectedIndexChanged += delegate {
                if (!settingLanguage) SetLanguage(languagePicker.SelectedIndex == 1 ? "zh-hans" : "en", true);
            };
            nav.Controls.Add(languagePicker);

            var top = new FlowLayoutPanel { Dock = DockStyle.Top, Height = 62, Padding = new Padding(16, 12, 4, 8), BackColor = Color.White };
            var back = new Button { Text = "←", Size = new Size(42, 32), FlatStyle = FlatStyle.Flat };
            back.Click += delegate { if (browser != null && browser.CanGoBack) browser.GoBack(); };
            var refresh = new Button { Text = "Refresh", Size = new Size(60, 32), FlatStyle = FlatStyle.Flat };
            refresh.Click += delegate { if (browser != null && browser.CoreWebView2 != null) { HideError(); browser.Reload(); } else StartBrowser(); };
            var demoLabel = new Label { Text = connection.IsDemo ? "Demo" : connection.IsSharedDemo ? "School demo" : "Main website", AutoSize = false, Width = 115, Height = 36,
                TextAlign = ContentAlignment.MiddleCenter, ForeColor = green };
            top.Controls.Add(back); top.Controls.Add(refresh); top.Controls.Add(demoLabel);
            var center = new Panel { Dock = DockStyle.Fill };
            center.Controls.Add(surface); center.Controls.Add(top);
            status.Padding = new Padding(14, 0, 0, 0);
            status.Text = "Connecting to your seller workspace...";
            center.Controls.Add(status);
            Controls.Add(center); Controls.Add(nav);
            SetLanguage(language, false);
            Shown += delegate { StartBrowser(); };
            FormClosed += delegate { if (browser != null) browser.Dispose(); };
        }

        private void TranslateControls(Control control)
        {
            if ((control is Button || control is Label || control == this) && control != status) {
                if (!originalLabels.ContainsKey(control)) originalLabels[control] = control.Text;
                control.Text = T(originalLabels[control]);
            }
            foreach (Control child in control.Controls) TranslateControls(child);
        }

        private void SetLanguage(string code, bool navigate)
        {
            language = SellerLocale.Normalize(code);
            System.Threading.Thread.CurrentThread.CurrentUICulture = System.Globalization.CultureInfo.GetCultureInfo(language == "zh-hans" ? "zh-CN" : "en-US");
            System.Threading.Thread.CurrentThread.CurrentCulture = System.Threading.Thread.CurrentThread.CurrentUICulture;
            settingLanguage = true;
            languagePicker.SelectedIndex = language == "zh-hans" ? 1 : 0;
            settingLanguage = false;
            TranslateControls(this);
            status.Text = connection.IsSharedDemo ? T("Shared school demo · No login · Products sync to the main website") : T("Connecting to your seller workspace...");
            try { Directory.CreateDirectory(Path.GetDirectoryName(LanguagePath)); File.WriteAllText(LanguagePath, language); hasLanguagePreference = true; } catch { }
            if (navigate && browser != null && browser.CoreWebView2 != null) {
                SetLanguageCookie(browser.CoreWebView2);
                browser.Reload();
            }
        }

        private void SetLanguageCookie(CoreWebView2 core)
        {
            var cookie = core.CookieManager.CreateCookie("django_language", language, origin.Host, "/");
            cookie.IsSecure = origin.Scheme == "https";
            core.CookieManager.AddOrUpdateCookie(cookie);
        }

        private static ConnectionSettings LoadConnection()
        {
            string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "app-settings.json");
            if (!File.Exists(path))
                return ConnectionSettings.FromValues(new Dictionary<string, string>());
            var parsed = new JavaScriptSerializer().Deserialize<Dictionary<string, string>>(File.ReadAllText(path));
            if (parsed == null) throw new ArgumentException("app-settings.json must contain a connection configuration.");
            return ConnectionSettings.FromValues(parsed);
        }

        private Button NavButton(string text)
        {
            return new Button { Text = text, Width = 160, Height = 46, Margin = new Padding(0, 5, 0, 5),
                BackColor = Color.FromArgb(51, 94, 75), ForeColor = Color.White, FlatStyle = FlatStyle.Flat, UseMnemonic = false,
                TextAlign = ContentAlignment.MiddleLeft, Padding = new Padding(12, 0, 0, 0) };
        }

        private void AddNav(FlowLayoutPanel nav, string label, string path)
        {
            var button = NavButton(label);
            button.Click += delegate { Navigate(path); };
            nav.Controls.Add(button);
        }

        private void Navigate(string path)
        {
            if (browser == null || browser.CoreWebView2 == null || origin == null) return;
            HideError();
            browser.CoreWebView2.Navigate(new Uri(origin, path).ToString());
        }

        private async void StartBrowser()
        {
            if (switching) return;
            switching = true;
            try {
                string url = overrideOrigin ?? connection.Origin;
                origin = new Uri(url.TrimEnd('/') + "/");
                status.Text = connection.IsDemo ? T("Demo data · Payment and shipping are simulated")
                    : connection.IsSharedDemo ? T("Shared school demo · No login · Products sync to the main website")
                    : "Main website: " + origin.Host + " · Sign in with your seller account";
                if (browser != null) { browser.Dispose(); browser = null; }
                surface.Controls.Clear();
                browser = new WebView2 { Dock = DockStyle.Fill, DefaultBackgroundColor = Color.White };
                surface.Controls.Add(browser);
                string data = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "AtelierSeller", "WebView", ConnectionPolicy.ProfileName(origin));
                var options = new CoreWebView2EnvironmentOptions { Language = language == "zh-hans" ? "zh-CN" : "en-US" };
                var environment = await CoreWebView2Environment.CreateAsync(null, data, options);
                await browser.EnsureCoreWebView2Async(environment);
                var core = browser.CoreWebView2;
                // Fetch current server routes after an application/server update;
                // retain cookies while discarding stale permanent-redirect cache.
                await core.Profile.ClearBrowsingDataAsync(CoreWebView2BrowsingDataKinds.DiskCache);
                core.Settings.IsWebMessageEnabled = false;
                core.Settings.AreHostObjectsAllowed = false;
                core.Settings.AreDevToolsEnabled = false;
                core.Settings.AreBrowserAcceleratorKeysEnabled = false;
                core.Settings.IsPasswordAutosaveEnabled = false;
                core.Settings.IsGeneralAutofillEnabled = false;
                core.Settings.UserAgent += " AtelierSeller/1.4.0";
                if (hasLanguagePreference) SetLanguageCookie(core);
                core.PermissionRequested += delegate(object sender, CoreWebView2PermissionRequestedEventArgs e) {
                    e.State = CoreWebView2PermissionState.Deny;
                };
                core.NewWindowRequested += delegate(object sender, CoreWebView2NewWindowRequestedEventArgs e) {
                    e.Handled = true;
                    if (!e.IsUserInitiated) return;
                    if (ConnectionPolicy.SameOrigin(origin, e.Uri)) core.Navigate(e.Uri);
                    else OpenExternal(e.Uri);
                };
                core.NavigationStarting += delegate(object sender, CoreWebView2NavigationStartingEventArgs e) {
                    if (!ConnectionPolicy.SameOrigin(origin, e.Uri)) {
                        e.Cancel = true;
                        status.Text = T("Navigation to another website was blocked. Use your browser to view external links.");
                    }
                };
                core.DownloadStarting += delegate(object sender, CoreWebView2DownloadStartingEventArgs e) {
                    e.Cancel = true;
                    status.Text = T("To download a file, choose Open in browser.");
                };
                core.NavigationCompleted += async delegate(object sender, CoreWebView2NavigationCompletedEventArgs e) {
                    if (e.IsSuccess) {
                        try {
                            string pageLanguage = new JavaScriptSerializer().Deserialize<string>(await core.ExecuteScriptAsync("document.documentElement.lang"));
                            SetLanguage(pageLanguage, false);
                        } catch { }
                    }
                    if (!e.IsSuccess && e.WebErrorStatus != CoreWebView2WebErrorStatus.OperationCanceled)
                        ShowError("Cannot connect to the seller service", "Check your connection, then choose Refresh. The website must remain online.\nError: " + e.WebErrorStatus);
                };
                core.ProcessFailed += delegate { ShowError("The page stopped responding", "Choose Refresh to reconnect. Your server records are unaffected."); };
                core.Navigate(new Uri(origin, connection.StartPath).ToString());
            }
            catch (WebView2RuntimeNotFoundException) {
                ShowError("Microsoft Edge WebView2 is required", "Install Microsoft WebView2 Runtime, then reopen the app.\nSee README.txt for the official download link.");
            }
            catch (Exception e) { ShowError("The app could not start", "Please reopen the app. Error: " + e.GetType().Name); }
            finally { switching = false; }
        }

        private void NewDemo()
        {
            if (browser == null || browser.CoreWebView2 == null) return;
            if (MessageBox.Show(T("Start a new demo shop? Your current sample records will stay on the server."),
                T("New demo"), MessageBoxButtons.OKCancel, MessageBoxIcon.Question) != DialogResult.OK) return;
            browser.CoreWebView2.CookieManager.DeleteAllCookies();
            browser.CoreWebView2.Navigate(origin.ToString());
        }

        private void HideError()
        {
            Control error = surface.Controls["connection-error"];
            if (error != null) { surface.Controls.Remove(error); error.Dispose(); }
            if (browser != null) browser.Visible = true;
        }

        private void ShowError(string title, string details)
        {
            HideError();
            if (browser != null) browser.Visible = false;
            var panel = new FlowLayoutPanel { Name = "connection-error", Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown,
                WrapContents = false, Padding = new Padding(40, 60, 25, 25), BackColor = Color.White };
            panel.Controls.Add(new Label { Text = T(title), AutoSize = true, Font = new Font(Font.FontFamily, 20F, FontStyle.Bold), ForeColor = green });
            panel.Controls.Add(new Label { Text = language == "zh-hans" ? "请检查网络连接后重试。服务器中的商品和订单会保留。" : details, AutoSize = true, MaximumSize = new Size(700, 0), Margin = new Padding(0, 24, 0, 24) });
            var retry = new Button { Text = T("Reconnect"), Size = new Size(130, 42) };
            retry.Click += delegate { StartBrowser(); };
            panel.Controls.Add(retry);
            surface.Controls.Add(panel);
            panel.BringToFront();
        }

        private void OpenExternal(string value)
        {
            Uri uri;
            if (!Uri.TryCreate(value, UriKind.Absolute, out uri) || !String.IsNullOrEmpty(uri.UserInfo)
                || (uri.Scheme != "https" && !(uri.Scheme == "http" && ConnectionPolicy.SameOrigin(origin, value)))) return;
            Process.Start(new ProcessStartInfo(uri.ToString()) { UseShellExecute = true });
        }
    }
}
