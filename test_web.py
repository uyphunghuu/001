import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'data'))

# Test page_dashboard rendering
from web_silver import page_dashboard
html = page_dashboard()
print('RENDER OK, length:', len(html))
print('First 200 chars:', html[:200])
