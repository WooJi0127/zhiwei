"""Run the existing browser smoke suite plus real backup-file import interactions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import smoke_test

# The owner now requires search to start collapsed. Adapt the legacy inline-style
# expectation and open search through its real button before running its search case.
smoke_test.INJECT = smoke_test.INJECT.replace(
    'step(function(){',
    'step(function(){ LOG.push("初始搜索收起=" + !vis("searchCover")); });\nstep(function(){', 1)
smoke_test.INJECT = smoke_test.INJECT.replace(
    '$("q").value = "A2O";', '$("searchToggle").click(); $("q").value = "A2O";')
smoke_test.INJECT = smoke_test.INJECT.replace(
    'LOG.push("搜索框展开=" + ($("searchCover").style.display !== "none"));',
    'LOG.push("搜索按需收起=" + !vis("searchCover"));')
smoke_test.REQUIRED = [
    ("搜索按需收起=true", "关闭后搜索仍显示") if expected == "搜索框展开=true" else (expected, message)
    for expected, message in smoke_test.REQUIRED
]
smoke_test.REQUIRED.append(("初始搜索收起=true", "首次打开搜索未收起"))

EXTRA = r'''
step(function(){
  document.querySelector('[data-tab="mine"]').click();
  LOG.push("备份入口=" + !!($('exportBackup') && $('importBackup')));
  var f = new File([JSON.stringify(window.ZWBackup.create(['historical-test-id'], ['Example Test Artist']))], 'backup.json', {type:'application/json'});
  var dt = new DataTransfer(); dt.items.add(f);
  $('backupFile').files = dt.files;
  $('backupFile').dispatchEvent(new Event('change'));
});
step(function(){
  LOG.push("导入已保存=" + (JSON.parse(localStorage.getItem('zw_favs')).indexOf('historical-test-id') >= 0));
  LOG.push("本命已保存=" + (JSON.parse(localStorage.getItem('zw_bias')).indexOf('Example Test Artist') >= 0));
  var dt = new DataTransfer(); dt.items.add(new File(['{"version":999}'], 'bad.json'));
  $('backupFile').files = dt.files; $('backupFile').dispatchEvent(new Event('change'));
});
step(function(){
  LOG.push("错误备份未覆盖=" + (JSON.parse(localStorage.getItem('zw_favs')).indexOf('historical-test-id') >= 0 && $('backupStatus').textContent.indexOf('未导入') >= 0));
  LOG.push("我的无横向溢出=" + (document.documentElement.scrollWidth <= document.documentElement.clientWidth));
  history.pushState(null,'','#release=%E0%A4%A');
  dispatchEvent(new PopStateEvent('popstate'));
  LOG.push("损坏链接可恢复=" + ($('homeView').style.display !== 'none'));
});
'''
smoke_test.INJECT = smoke_test.INJECT.replace('function next(){', EXTRA + '\nfunction next(){')
smoke_test.REQUIRED += [(x + '=true', x) for x in ['备份入口','导入已保存','本命已保存','错误备份未覆盖','我的无横向溢出','损坏链接可恢复']]
raise SystemExit(smoke_test.main())
