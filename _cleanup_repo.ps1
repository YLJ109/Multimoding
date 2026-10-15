# 清掉半途失败的 ppt-master 克隆目录，便于重新克隆
$target = 'D:\PythonProjections\MultimodingProject\_ppt_master_repo'
if (Test-Path -LiteralPath $target) {
    $resolved = (Resolve-Path -LiteralPath $target).Path
    if ($resolved -ne $target) { throw "路径不符合预期: $resolved" }
    Remove-Item -LiteralPath $resolved -Recurse -Force
    Write-Output "removed: $resolved"
}
else { Write-Output 'nothing to remove' }
