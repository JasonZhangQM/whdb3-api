"""最终验证 warrant 拆分。"""
import sys
sys.path.insert(0, ".")
from app.warrant.services import warrant_service, ext_service

# warrant_service API 层用到的
main = ['list_warrants','get_detail','create','update','delete','batch_storage','batch_transfer','batch_cancel','submit_release_out_request','get_release_out_pending','submit_lend_out_request','get_lend_out_pending','stats_overview','stats_by_customer','list_storages','add_storage','list_evaluates','add_evaluate','add_recheck','list_evaluate_companies','create_evaluate_company','delete_evaluate_company']
# ext_service API 层用到的
ext = ['list_owners','add_owner','update_owner','delete_owner','get_type_detail','update_type_detail','add_house','delete_house','add_ground','delete_ground','add_construction','delete_construction','list_draft_extends','add_draft_extend','update_draft_extend','delete_draft_extend','list_receive_extends','add_receive_extend','delete_receive_extend','create_ext']

missing_m = [f for f in main if not hasattr(warrant_service, f)]
missing_e = [f for f in ext if not hasattr(ext_service, f)]

print(f"warrant_service: {len(main) - len(missing_m)}/{len(main)}")
if missing_m: print(f"  ❌ missing: {missing_m}")
print(f"ext_service:     {len(ext) - len(missing_e)}/{len(ext)}")
if missing_e: print(f"  ❌ missing: {missing_e}")

from app.main import app
print(f"\nFastAPI routes: {len(app.routes)}")
print("✅ PASS" if not missing_m and not missing_e else "❌ FAIL")
