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
[assembly: System.Reflection.AssemblyVersion("1.2.0.0")]

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

    internal sealed class SellerWindow : Form
    {
        private readonly Color green = Color.FromArgb(37, 79, 62);
        private readonly Panel surface = new Panel { Dock = DockStyle.Fill, BackColor = Color.White };
        private readonly Label status = new Label { Dock = DockStyle.Bottom, Height = 30, TextAlign = ContentAlignment.MiddleLeft };
        private readonly string demoOrigin;
        private WebView2 browser;
        private Uri origin;
        private bool switching;
        private string overrideOrigin;

        public SellerWindow(string[] args)
        {
            Text = "Atelier Seller";
            MinimumSize = new Size(920, 680);
            Size = new Size(1320, 900);
            StartPosition = FormStartPosition.CenterScreen;
            Font = new Font("Segoe UI", 9F);
            BackColor = Color.FromArgb(243, 246, 242);
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }
            demoOrigin = LoadDemoOrigin();
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
            var clear = NavButton("New demo");
            clear.Click += delegate { NewDemo(); };
            nav.Controls.Add(clear);
            var about = NavButton("Help");
            about.Click += delegate {
                MessageBox.Show("This coursework demo uses sample products and orders. No account is required.\n\nThe website and Windows app use the same demo service. Each browser session has its own sample shop.\n\nDeepSeek interprets natural-language requests. Review and confirm each proposed change before it is saved to the demo database.\n\nPayments and shipments are simulated. Nothing is charged and no parcel is sent.\n\nTry My products, New listing, and My orders. Internet access and the demo server are required.",
                    "Help", MessageBoxButtons.OK, MessageBoxIcon.Information);
            };
            nav.Controls.Add(about);

            var top = new FlowLayoutPanel { Dock = DockStyle.Top, Height = 62, Padding = new Padding(16, 12, 4, 8), BackColor = Color.White };
            var back = new Button { Text = "←", Size = new Size(42, 32), FlatStyle = FlatStyle.Flat };
            back.Click += delegate { if (browser != null && browser.CanGoBack) browser.GoBack(); };
            var refresh = new Button { Text = "Refresh", Size = new Size(60, 32), FlatStyle = FlatStyle.Flat };
            refresh.Click += delegate { if (browser != null && browser.CoreWebView2 != null) { HideError(); browser.Reload(); } else StartBrowser(); };
            var demoLabel = new Label { Text = "Demo", AutoSize = false, Width = 75, Height = 36,
                TextAlign = ContentAlignment.MiddleCenter, ForeColor = green };
            top.Controls.Add(back); top.Controls.Add(refresh); top.Controls.Add(demoLabel);
            var center = new Panel { Dock = DockStyle.Fill };
            center.Controls.Add(surface); center.Controls.Add(top);
            status.Padding = new Padding(14, 0, 0, 0);
            status.Text = "Connecting to your seller workspace...";
            center.Controls.Add(status);
            Controls.Add(center); Controls.Add(nav);
            Shown += delegate { StartBrowser(); };
            FormClosed += delegate { if (browser != null) browser.Dispose(); };
        }

        private static string LoadDemoOrigin()
        {
            string result = "https://demo.maijiax.cn";
            string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "app-settings.json");
            try {
                var parsed = new JavaScriptSerializer().Deserialize<Dictionary<string, string>>(File.ReadAllText(path));
                if (parsed.ContainsKey("demoOrigin") && ConnectionPolicy.IsAllowedOrigin(parsed["demoOrigin"]))
                    result = parsed["demoOrigin"].TrimEnd('/');
            } catch { }
            return result;
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
                string url = overrideOrigin ?? demoOrigin;
                origin = new Uri(url.TrimEnd('/') + "/");
                status.Text = "Demo data · Payment and shipping are simulated";
                if (browser != null) { browser.Dispose(); browser = null; }
                surface.Controls.Clear();
                browser = new WebView2 { Dock = DockStyle.Fill, DefaultBackgroundColor = Color.White };
                surface.Controls.Add(browser);
                string data = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "AtelierSeller", "WebView", ConnectionPolicy.ProfileName(origin));
                var options = new CoreWebView2EnvironmentOptions { Language = "en-US" };
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
                core.Settings.UserAgent += " AtelierSeller/1.2.0";
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
                        status.Text = "Navigation to another website was blocked. Use your browser to view external links.";
                    }
                };
                core.DownloadStarting += delegate(object sender, CoreWebView2DownloadStartingEventArgs e) {
                    e.Cancel = true;
                    status.Text = "To download a file, choose Open in browser.";
                };
                core.NavigationCompleted += delegate(object sender, CoreWebView2NavigationCompletedEventArgs e) {
                    if (!e.IsSuccess && e.WebErrorStatus != CoreWebView2WebErrorStatus.OperationCanceled)
                        ShowError("Cannot connect to the seller service", "Check your connection, then choose Refresh. The demo server must remain online.\nError: " + e.WebErrorStatus);
                };
                core.ProcessFailed += delegate { ShowError("The page stopped responding", "Choose Refresh to reconnect. Your server records are unaffected."); };
                core.Navigate(origin.ToString());
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
            if (MessageBox.Show("Start a new demo shop? Your current sample records will stay on the server.",
                "New demo", MessageBoxButtons.OKCancel, MessageBoxIcon.Question) != DialogResult.OK) return;
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
            panel.Controls.Add(new Label { Text = title, AutoSize = true, Font = new Font(Font.FontFamily, 20F, FontStyle.Bold), ForeColor = green });
            panel.Controls.Add(new Label { Text = details, AutoSize = true, MaximumSize = new Size(700, 0), Margin = new Padding(0, 24, 0, 24) });
            var retry = new Button { Text = "Reconnect", Size = new Size(130, 42) };
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
