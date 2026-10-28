using System;
using System.Collections.Generic;
using AtelierSeller;

internal static class PolicyTests
{
    private static void Check(bool condition, string message) { if (!condition) throw new Exception(message); }
    private static void Main()
    {
        Check(ConnectionPolicy.IsAllowedOrigin("https://seller.maijiax.cn"), "HTTPS origin");
        Check(ConnectionPolicy.IsAllowedOrigin("http://127.0.0.1:8784"), "loopback preview");
        foreach (var bad in new[] { "http://example.com", "file:///C:/secret", "javascript:alert(1)",
            "https://user:pass@example.com", "https://example.com/?token=x", "https://example.com/other" })
            Check(!ConnectionPolicy.IsAllowedOrigin(bad), "Rejected: " + bad);
        var origin = new Uri("https://seller.maijiax.cn");
        Check(ConnectionPolicy.SameOrigin(origin, "https://seller.maijiax.cn/seller/ai/"), "Own page");
        foreach (var bad in new[] { "https://seller.maijiax.cn.evil.test/", "http://seller.maijiax.cn/", "https://seller.maijiax.cn:444/", "https://u@seller.maijiax.cn/" })
            Check(!ConnectionPolicy.SameOrigin(origin, bad), "Blocked navigation: " + bad);
        Check(ConnectionPolicy.ProfileName(origin) != ConnectionPolicy.ProfileName(new Uri("http://127.0.0.1:8784")), "Separate sessions");
        var live = ConnectionSettings.FromValues(new Dictionary<string, string> {
            { "origin", "https://seller.maijiax.cn/" }, { "mode", "live" }
        });
        Check(!live.IsDemo && live.Origin == "https://seller.maijiax.cn", "Main website configuration");
        Check(live.StartPath == "/seller/ai/", "Main website opens authenticated assistant");
        var legacy = ConnectionSettings.FromValues(new Dictionary<string, string> {
            { "demoOrigin", "https://demo.maijiax.cn" }
        });
        Check(legacy.IsDemo && legacy.StartPath == "/", "Legacy demo remains compatible");
        var shared = new ConnectionSettings("https://dip-new-repo.vercel.app", "shared-demo");
        Check(shared.IsSharedDemo && !shared.IsDemo && shared.StartPath == "/seller/ai/", "Shared school demo opens directly");
        foreach (var mode in new[] { "production", "", "LIVE" }) {
            bool rejected = false;
            try { new ConnectionSettings("https://seller.maijiax.cn", mode); }
            catch (ArgumentException) { rejected = true; }
            Check(rejected, "Reject ambiguous connection mode");
        }
        Console.WriteLine("21 desktop connection and session policy checks passed.");
    }
}
