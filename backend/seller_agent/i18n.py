from django.utils.translation import get_language, gettext


def language():
    return 'zh-hans' if (get_language() or '').lower().startswith('zh') else 'en'


TEXT = {
    'you': 'You', 'assistant': 'Seller assistant', 'web': 'Website', 'mini': 'Mini Program',
    'thinking': 'Thinking…', 'products': 'Products', 'orders': 'Orders', 'refresh': 'Refresh',
    'conversation': 'Conversation', 'helpTitle': 'How can I help with your shop?',
    'helpText': 'Ask for your stock or orders, or start a new product draft.',
    'draft': 'Creates an unpublished draft', 'review': 'Review these values carefully',
    'approve': 'I reviewed and approve this exact change.', 'confirm': 'Confirm change',
    'editor': 'Open product editor', 'retry': 'Prepare a fresh preview to make a change.',
    'noChanges': 'Proposed changes appear here. Nothing is applied until you confirm.',
    'guided': 'Guided mode', 'deepseek': 'DeepSeek AI', 'catalogue': 'Main website catalogue',
    'demoShop': 'Demo shop', 'linked': 'Verified seller', 'unlinked': 'Unlinked account',
    'active': 'Active', 'unpublished': 'Unpublished', 'madeToOrder': 'Made to order',
    'available': '{n} available', 'option': 'Option', 'standard': 'Standard',
    'selectOption': 'Select an option for stock updates', 'quantity': 'New available quantity',
    'stockPreview': 'Preview stock change', 'price': 'New price', 'pricePreview': 'Preview price change',
    'editProduct': 'Edit photos, options and publication', 'noProducts': 'No matching products.',
    'carrier': 'Carrier', 'carrierName': 'Carrier name', 'tracking': 'Tracking number',
    'shipPreview': 'Preview shipment', 'noOrders': 'No orders for your shop.',
    'delivery': 'Confirm delivery', 'deliveryPreview': 'Preview delivery confirmation',
    'delivered': 'Delivered',
    'approvalRequired': 'Review the exact change and tick the approval box first.',
    'serverError': 'The server could not complete this request.',
    'validation': 'Validation failed.', 'sessionExpired': 'Refresh the page before continuing.',
    'missing': 'Still needed', 'name': 'Name', 'category': 'Category',
    'description': 'Description', 'quantityField': 'Quantity',
    'stock': 'Stock', 'listing': 'New product', 'fulfillment': 'Shipment',
    'pending': 'Pending', 'applied': 'Applied', 'superseded': 'Replaced', 'expired': 'Expired',
    'paid': 'Paid', 'unpaid': 'Unpaid', 'failed': 'Failed', 'refunded': 'Refunded',
    'partial': 'Partially shipped', 'unfulfilled': 'Not shipped', 'fulfilled': 'Shipped',
    'unknown': 'Unknown', 'saved': 'Product updated.',
    'sharedStatus': 'No login needed · Shared main website data',
    'sampleStatus': 'Sample shop · no account needed',
    'verifiedStatus': 'Verified seller · the same shop is used by both channels',
    'verificationRequired': 'Account linked · seller verification is still required',
    'guidedStatus': 'Guided mode · no AI-provider calls',
    'aiStatus': 'DeepSeek AI enabled · changes require your confirmation',
}


def ui_strings():
    return {key: gettext(value) for key, value in TEXT.items()}
