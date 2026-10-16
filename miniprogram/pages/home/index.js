const api = require('../../utils/seller-api');
const info = require('../../public-config');
Page({
  data:{info,agreed:false},
  onShow(){this.setData({agreed:api.hasConsent()});},
  consentChanged(e){this.setData({agreed:e.detail.value.includes('agree')});},
  privacy(){wx.navigateTo({url:'/pages/privacy/index'});},
  enter(){if(!this.data.agreed)return;api.write('privacy-consent',info.privacyVersion);wx.navigateTo({url:'/pages/seller/index'});},
  contact(){if(info.contact)wx.setClipboardData({data:info.contact});}
});
