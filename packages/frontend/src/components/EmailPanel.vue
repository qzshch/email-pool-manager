<template>
  <div class="h-full flex flex-col overflow-hidden">
    <!-- 统计条 -->
    <div class="px-4 pt-3 pb-2 shrink-0">
      <div class="flex items-center gap-3 text-xs text-slate-400">
        <span>总计 <b class="text-slate-200">{{ stats.total }}</b></span>
        <span class="text-emerald-400">存活 <b>{{ stats.active }}</b></span>
        <span class="text-rose-400">死亡 <b>{{ stats.dead }}</b></span>
        <span class="text-amber-400">待检 <b>{{ stats.unknown }}</b></span>
        <span class="ml-auto text-[10px] text-slate-500">
          mail.tm {{ stats.by_provider?.mail_tm || 0 }} · tempmail {{ stats.by_provider?.tempmail_lol || 0 }} · imap {{ stats.by_provider?.imap || 0 }}
        </span>
        <button
          class="text-slate-400 hover:text-indigo-400"
          title="刷新统计"
          @click="refreshAll"
        >
          <el-icon><Refresh /></el-icon>
        </button>
      </div>
    </div>

    <!-- 工具行 -->
    <div class="px-4 pb-2 space-y-2 shrink-0">
      <div class="flex gap-2 items-center">
        <el-select v-model="createProvider" class="!w-32" size="small">
          <el-option label="Mail.tm" value="mail_tm" />
          <el-option label="Tempmail.lol" value="tempmail_lol" />
        </el-select>
        <el-input-number v-model="createCount" :min="1" :max="50" size="small" class="!w-24" controls-position="right" />
        <button
          class="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors disabled:opacity-50"
          :disabled="taskRunning"
          @click="onBatchCreate"
        >
          批量创建
        </button>
        <button
          class="px-3 py-1.5 rounded-lg border border-slate-600/80 text-slate-300 hover:text-white hover:bg-slate-800 text-xs font-medium transition-colors disabled:opacity-50"
          :disabled="taskRunning"
          @click="onCheckAll"
        >
          全部探活
        </button>
        <button
          class="px-3 py-1.5 rounded-lg border border-slate-600/80 text-slate-300 hover:text-white hover:bg-slate-800 text-xs font-medium transition-colors"
          @click="importDialogVisible = true"
        >
          导入 IMAP
        </button>
        <button
          class="px-3 py-1.5 rounded-lg border border-slate-600/80 text-slate-300 hover:text-white hover:bg-slate-800 text-xs font-medium transition-colors"
          @click="onExport"
        >
          导出
        </button>
      </div>
      <div class="flex gap-2 items-center">
        <el-input
          v-model="search"
          size="small"
          placeholder="搜索邮箱地址"
          clearable
          class="!w-48"
          :prefix-icon="Search"
        />
        <el-select v-model="statusFilter" size="small" class="!w-28" clearable placeholder="状态">
          <el-option label="存活" value="active" />
          <el-option label="死亡" value="dead" />
          <el-option label="待检" value="unknown" />
        </el-select>
        <el-select v-model="providerFilter" size="small" class="!w-32" clearable placeholder="类型">
          <el-option label="Mail.tm" value="mail_tm" />
          <el-option label="Tempmail.lol" value="tempmail_lol" />
          <el-option label="IMAP" value="imap" />
        </el-select>
        <span v-if="taskRunning" class="text-[10px] text-amber-400 ml-auto">
          {{ taskStatus.kind === 'batch_create' ? '批量创建中' : '探活中' }} {{ taskStatus.done }}/{{ taskStatus.total }}
        </span>
      </div>
    </div>

    <!-- 池设置 -->
    <div class="px-4 pb-2 shrink-0">
      <div class="rounded-lg border border-slate-800/60 bg-slate-900/20 px-3 py-2 flex flex-wrap gap-2 items-center text-xs text-slate-400">
        <span class="text-[10px] uppercase tracking-wider text-slate-500">池设置</span>
        <span>探活间隔</span>
        <el-input-number v-model="poolCfg.checkIntervalHours" :min="0" :max="720" size="small" class="!w-24" controls-position="right" />
        <span>小时(0=关)</span>
        <span>目标存活</span>
        <el-input-number v-model="poolCfg.targetSize" :min="0" :max="200" size="small" class="!w-24" controls-position="right" />
        <span>(0=关)</span>
        <el-checkbox v-model="poolCfg.autoCapture" size="small">注册邮箱自动入池</el-checkbox>
        <button
          class="ml-auto px-2.5 py-1 rounded border border-slate-600/80 text-slate-300 hover:text-white hover:bg-slate-800 text-[11px]"
          :disabled="savingCfg"
          @click="savePoolCfg"
        >
          {{ savingCfg ? '保存中' : '保存设置' }}
        </button>
      </div>
    </div>

    <!-- 列表 -->
    <div class="flex-1 min-h-0 px-4">
      <el-table
        :data="emails"
        size="small"
        height="100%"
        :header-cell-style="tableHeaderCellStyle"
        class="dark-table"
      >
        <el-table-column label="邮箱" min-width="200">
          <template #default="{ row }">
            <div class="text-xs text-slate-200 truncate">{{ row.address }}</div>
            <div class="text-[10px] text-slate-500 truncate">{{ row.status_detail || '-' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="90">
          <template #default="{ row }">
            <span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">{{ providerLabel(row.provider) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="70">
          <template #default="{ row }">
            <span :class="statusClass(row.status)">{{ statusLabel(row.status) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="用途" min-width="110">
          <template #default="{ row }">
            <span class="text-xs text-slate-400">{{ row.purpose || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="最近探活" width="95">
          <template #default="{ row }">
            <span class="text-[10px] text-slate-500">{{ shortTime(row.last_checked_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <div class="flex items-center gap-1">
              <el-tooltip content="探活" placement="top">
                <button
                  class="p-1 rounded text-slate-400 hover:text-indigo-400 hover:bg-slate-800 disabled:opacity-40"
                  :disabled="checkingId === row.id"
                  @click="onCheckOne(row)"
                >
                  <span v-if="checkingId === row.id" class="inline-block w-3 h-3 border-2 border-slate-500 border-t-transparent rounded-full animate-spin"></span>
                  <el-icon v-else><CircleCheck /></el-icon>
                </button>
              </el-tooltip>
              <el-tooltip content="编辑用途" placement="top">
                <button
                  class="p-1 rounded text-slate-400 hover:text-amber-400 hover:bg-slate-800"
                  @click="openEdit(row)"
                >
                  <el-icon><Edit /></el-icon>
                </button>
              </el-tooltip>
              <el-popconfirm
                :title="row.provider === 'mail_tm' ? '删除（是否同时删除 mail.tm 远端账号？）' : '确认删除该邮箱？'"
                confirm-button-text="删除"
                cancel-button-text="取消"
                @confirm="onDelete(row)"
              >
                <template #reference>
                  <button class="p-1 rounded text-slate-400 hover:text-rose-400 hover:bg-slate-800">
                    <el-icon><Delete /></el-icon>
                  </button>
                </template>
              </el-popconfirm>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 分页 -->
    <div class="px-4 py-2 shrink-0 flex justify-center">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="prev, pager, next, sizes"
        small
        @current-change="fetchEmails"
        @size-change="fetchEmails"
      />
    </div>

    <!-- IMAP 导入对话框 -->
    <el-dialog v-model="importDialogVisible" title="导入 IMAP 邮箱" width="440px" append-to-body>
      <el-form label-width="90px" size="small">
        <el-form-item label="邮箱地址" required>
          <el-input v-model="importForm.address" placeholder="user@example.com" />
        </el-form-item>
        <el-form-item label="密码" required>
          <el-input v-model="importForm.password" type="password" show-password placeholder="授权码/密码" />
        </el-form-item>
        <el-form-item label="IMAP 主机" required>
          <el-input v-model="importForm.imapHost" placeholder="imap.qq.com" />
        </el-form-item>
        <el-form-item label="端口">
          <el-input-number v-model="importForm.imapPort" :min="1" :max="65535" controls-position="right" class="!w-32" />
        </el-form-item>
        <el-form-item label="用途">
          <el-input v-model="importForm.purpose" placeholder="备注用途（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <button class="px-3 py-1.5 rounded-lg text-slate-400 hover:text-white text-xs" @click="importDialogVisible = false">取消</button>
        <button
          class="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs"
          :disabled="importing"
          @click="onImport"
        >
          {{ importing ? '导入中' : '导入' }}
        </button>
      </template>
    </el-dialog>

    <!-- 编辑用途对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑用途" width="380px" append-to-body>
      <el-input v-model="editPurpose" placeholder="用途备注" />
      <template #footer>
        <button class="px-3 py-1.5 rounded-lg text-slate-400 hover:text-white text-xs" @click="editDialogVisible = false">取消</button>
        <button class="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs" @click="saveEdit">保存</button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheck, Delete, Edit, Refresh, Search } from '@element-plus/icons-vue'
import { emailApi, configApi } from '../api'
import { useAppStore } from '../stores/app'

const store = useAppStore()

const emails = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const search = ref('')
const statusFilter = ref('')
const providerFilter = ref('')

const stats = ref<any>({ total: 0, active: 0, dead: 0, unknown: 0, by_provider: {} })
const taskStatus = ref<any>({ running: false, kind: '', done: 0, total: 0, success: 0, fail: 0 })
const taskRunning = computed(() => taskStatus.value?.running === true)

const createProvider = ref('mail_tm')
const createCount = ref(3)

const poolCfg = reactive({ checkIntervalHours: 24, targetSize: 0, autoCapture: true })
const savingCfg = ref(false)

const checkingId = ref<number | null>(null)
const importDialogVisible = ref(false)
const importing = ref(false)
const importForm = reactive({ address: '', password: '', imapHost: 'imap.qq.com', imapPort: 993, purpose: '' })

const editDialogVisible = ref(false)
const editPurpose = ref('')
let editId = 0

const tableHeaderCellStyle = computed(() => ({
  background: store.theme === 'dark' ? '#1e293b' : '#f1f5f9',
  color: store.theme === 'dark' ? '#94a3b8' : '#475569',
  fontSize: '10px',
}))

function providerLabel(p: string) {
  return p === 'mail_tm' ? 'Mail.tm' : p === 'tempmail_lol' ? 'Tempmail' : 'IMAP'
}
function statusLabel(s: string) {
  return s === 'active' ? '存活' : s === 'dead' ? '死亡' : '待检'
}
function statusClass(s: string) {
  return s === 'active'
    ? 'text-[10px] text-emerald-400'
    : s === 'dead'
      ? 'text-[10px] text-rose-400'
      : 'text-[10px] text-amber-400'
}
function shortTime(v?: string | null) {
  if (!v) return '-'
  return v.replace('T', ' ').slice(5, 16)
}

async function fetchEmails() {
  try {
    const { data } = await emailApi.list({
      provider: providerFilter.value || undefined,
      status: statusFilter.value || undefined,
      search: search.value || undefined,
      page: page.value,
      page_size: pageSize.value,
    })
    emails.value = data.items || []
    total.value = data.total || 0
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '邮箱列表加载失败')
  }
}

async function fetchStats() {
  try {
    const { data } = await emailApi.stats()
    stats.value = data
  } catch {}
}

async function fetchTaskStatus() {
  try {
    const { data } = await emailApi.taskStatus()
    const wasRunning = taskRunning.value
    taskStatus.value = data
    if (wasRunning && data.running === false) {
      ElMessage.success(`池任务完成: 成功 ${data.success}, 失败 ${data.fail}`)
      refreshAll()
    }
  } catch {}
}

function refreshAll() {
  fetchEmails()
  fetchStats()
  fetchTaskStatus()
}

async function onBatchCreate() {
  try {
    await emailApi.batchCreate(createProvider.value, createCount.value)
    ElMessage.success(`批量创建已启动（${createProvider.value} × ${createCount.value}），看实时日志跟踪进度`)
    fetchTaskStatus()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '批量创建启动失败')
  }
}

async function onCheckAll() {
  try {
    await emailApi.checkAll()
    ElMessage.success('全量探活已启动')
    fetchTaskStatus()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '探活启动失败')
  }
}

async function onCheckOne(row: any) {
  checkingId.value = row.id
  try {
    const { data } = await emailApi.check(row.id)
    if (data.alive) ElMessage.success(`${row.address} 存活`)
    else ElMessage.warning(`${row.address} 已死亡: ${data.detail}`)
    fetchEmails()
    fetchStats()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '探活失败')
  } finally {
    checkingId.value = null
  }
}

async function onDelete(row: any) {
  try {
    const purgeRemote = row.provider === 'mail_tm'
    const { data } = await emailApi.remove(row.id, purgeRemote)
    ElMessage.success(data.message || '已删除')
    refreshAll()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

async function onImport() {
  importing.value = true
  try {
    await emailApi.import({
      provider: 'imap',
      address: importForm.address,
      password: importForm.password,
      imap_host: importForm.imapHost,
      imap_port: importForm.imapPort,
      purpose: importForm.purpose,
    })
    ElMessage.success('已导入，建议立即探活')
    importDialogVisible.value = false
    importForm.address = ''
    importForm.password = ''
    importForm.purpose = ''
    refreshAll()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '导入失败')
  } finally {
    importing.value = false
  }
}

function openEdit(row: any) {
  editId = row.id
  editPurpose.value = row.purpose || ''
  editDialogVisible.value = true
}

async function saveEdit() {
  try {
    await emailApi.update(editId, { purpose: editPurpose.value })
    ElMessage.success('已更新')
    editDialogVisible.value = false
    fetchEmails()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '更新失败')
  }
}

async function loadPoolCfg() {
  try {
    const { data } = await configApi.get()
    poolCfg.checkIntervalHours = data.email_pool_check_interval_hours ?? 24
    poolCfg.targetSize = data.email_pool_target_size ?? 0
    poolCfg.autoCapture = data.email_pool_auto_capture !== false
  } catch {}
}

async function savePoolCfg() {
  savingCfg.value = true
  try {
    const { data } = await configApi.get()
    await configApi.update({
      ...data,
      email_pool_check_interval_hours: poolCfg.checkIntervalHours,
      email_pool_target_size: poolCfg.targetSize,
      email_pool_auto_capture: poolCfg.autoCapture,
    })
    ElMessage.success('池设置已保存')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingCfg.value = false
  }
}

async function onExport() {
  try {
    const { data } = await emailApi.list({
      page: 1,
      page_size: 1000,
      include_secret: true,
      provider: providerFilter.value || undefined,
      status: statusFilter.value || undefined,
    })
    const blob = new Blob([JSON.stringify(data.items ?? [], null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `email-pool-export-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    ElMessage.error('导出失败')
  }
}

let searchDebounce: ReturnType<typeof setTimeout> | undefined
watch(search, () => {
  clearTimeout(searchDebounce)
  searchDebounce = setTimeout(() => {
    page.value = 1
    fetchEmails()
  }, 300)
})
watch([statusFilter, providerFilter], () => {
  page.value = 1
  fetchEmails()
})

let pollTimer: ReturnType<typeof setInterval>
onMounted(() => {
  loadPoolCfg()
  refreshAll()
  pollTimer = setInterval(() => {
    fetchTaskStatus()
    fetchStats()
  }, 15000)
})
onUnmounted(() => clearInterval(pollTimer))
</script>
