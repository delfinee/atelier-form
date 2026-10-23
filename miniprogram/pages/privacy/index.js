const info = require('../../public-config');
Page({data:{info},contact(){if(info.contact)wx.setClipboardData({data:info.contact});}});
