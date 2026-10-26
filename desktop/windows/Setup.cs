using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Windows.Forms;

internal sealed class SellerSetup : Form
{
    private readonly TextBox folder = new TextBox { Width = 445 };
    private readonly CheckBox shortcut = new CheckBox { Text = "Create a desktop shortcut", Checked = true, AutoSize = true };
    private readonly Button install = new Button { Text = "Install", Width = 140, Height = 38 };

    [STAThread]
    private static void Main()
    {
        System.Threading.Thread.CurrentThread.CurrentUICulture = System.Globalization.CultureInfo.GetCultureInfo("en-US");
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new SellerSetup());
    }

    private SellerSetup()
    {
        Text = "Install Atelier Seller Coursework Demo";
        ClientSize = new Size(620, 345);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 9F);
        BackColor = Color.FromArgb(244, 247, 242);
        var flow = new FlowLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(28), FlowDirection = FlowDirection.TopDown, WrapContents = false };
        flow.Controls.Add(new Label { Text = "Atelier Seller 1.2.0", AutoSize = true, Font = new Font(Font.FontFamily, 20, FontStyle.Bold), ForeColor = Color.FromArgb(37, 79, 62) });
        flow.Controls.Add(new Label { Text = "Coursework demo · Products, orders and DeepSeek AI.\nNo account needed. Payment and shipping are simulated.", Width = 530, Height = 60, Padding = new Padding(0, 12, 0, 0) });
        flow.Controls.Add(new Label { Text = "Install location (no administrator access required)", AutoSize = true });
        folder.Text = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "AtelierSeller");
        if (Directory.Exists(@"D:\")) folder.Text = @"D:\Apps\AtelierSeller";
        var row = new FlowLayoutPanel { Width = 540, Height = 43 };
        row.Controls.Add(folder);
        var browse = new Button { Text = "Browse", Width = 76 };
        browse.Click += delegate {
            using (var picker = new FolderBrowserDialog { Description = "Choose a dedicated folder for Atelier Seller", SelectedPath = folder.Text })
                if (picker.ShowDialog() == DialogResult.OK) folder.Text = picker.SelectedPath;
        };
        row.Controls.Add(browse);
        flow.Controls.Add(row);
        flow.Controls.Add(shortcut);
        install.Margin = new Padding(0, 15, 0, 0);
        install.Click += delegate { InstallApp(); };
        flow.Controls.Add(install);
        Controls.Add(flow);
    }

    private void InstallApp()
    {
        try {
            string target = Path.GetFullPath(folder.Text.Trim());
            if (target == Path.GetPathRoot(target) ||
                (Directory.Exists(target) && Directory.GetFileSystemEntries(target).Length > 0 && !File.Exists(Path.Combine(target, ".atelier-seller"))))
                throw new InvalidOperationException("Choose an empty folder or an existing AtelierSeller installation.");
            install.Enabled = false;
            Directory.CreateDirectory(target);
            using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("seller-payload.zip"))
            using (var archive = new ZipArchive(stream, ZipArchiveMode.Read)) {
                foreach (var entry in archive.Entries) {
                    string output = Path.GetFullPath(Path.Combine(target, entry.FullName));
                    if (!output.StartsWith(target.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidOperationException("The installation package contains an invalid path.");
                    if (entry.Name.Length == 0) { Directory.CreateDirectory(output); continue; }
                    Directory.CreateDirectory(Path.GetDirectoryName(output));
                    using (var input = entry.Open())
                    using (var file = File.Create(output)) input.CopyTo(file);
                }
            }
            if (shortcut.Checked) {
                Type shellType = Type.GetTypeFromProgID("WScript.Shell");
                object shell = Activator.CreateInstance(shellType);
                string linkPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "Atelier Seller.lnk");
                object link = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { linkPath });
                Type linkType = link.GetType();
                linkType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, link, new object[] { Path.Combine(target, "AtelierSeller.exe") });
                linkType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, link, new object[] { target });
                linkType.InvokeMember("Save", BindingFlags.InvokeMethod, null, link, new object[0]);
                System.Runtime.InteropServices.Marshal.ReleaseComObject(link);
                System.Runtime.InteropServices.Marshal.ReleaseComObject(shell);
            }
            if (MessageBox.Show("Installation complete. Open Atelier Seller now?", Text, MessageBoxButtons.YesNo, MessageBoxIcon.Information) == DialogResult.Yes)
                Process.Start(new ProcessStartInfo(Path.Combine(target, "AtelierSeller.exe")) { UseShellExecute = true, WorkingDirectory = target });
            Close();
        }
        catch (Exception ex) { install.Enabled = true; MessageBox.Show(ex.Message, "Installation could not be completed", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
    }
}
