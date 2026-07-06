import sys
sys.path.insert(0, '.')
from silver.utils.minio_helper import MinioHelper

m = MinioHelper()
objs = m.list_objects('gmail-raw')
for o in objs:
    key = o["object_key"]
    print(f'{key} ({o["size"]} bytes)')
print(f'Total: {len(objs)} objects')
