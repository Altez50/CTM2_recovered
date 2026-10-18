<template>
  <section class="panel access-page">
    <h2>Пользователи и доступ</h2>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="message" role="status">{{ message }}</p>
    <p v-if="!auth.canManageAccess">Настройка доступа доступна администратору без ограничения организаций.</p>
    <template v-else>
      <label>Пользователь <select v-model="selectedId" aria-label="Пользователь" @change="selectUser">
        <option :value="0">Новый пользователь</option>
        <option v-for="user in users" :key="user.id" :value="user.id">{{ user.username }}</option>
      </select></label>
      <template v-if="!selectedId">
        <label>Имя пользователя <input v-model="username" autocomplete="off" /></label>
        <label>Пароль <input v-model="password" type="password" autocomplete="new-password" minlength="8" /></label>
      </template>
      <label>Роль <select v-model="role" aria-label="Роль" :disabled="selectedId === auth.user?.id">
        <option value="viewer">Только чтение</option><option value="manager">Менеджер</option>
        <option value="foreman">Прораб</option><option value="admin">Администратор</option>
      </select></label>
      <label><input v-model="unrestricted" type="checkbox" :disabled="selectedId === auth.user?.id" /> Все организации</label>
      <p>Ограниченный доступ без выбранных организаций запрещает чтение и изменение торговых документов.</p>
      <fieldset v-if="!unrestricted" :disabled="selectedId === auth.user?.id"><legend>Разрешенные организации</legend>
        <label v-for="org in orgs" :key="org.id"><input v-model="allowed" type="checkbox" :value="org.id" /> {{ org.name }}</label>
      </fieldset>
      <button class="button button-primary" :disabled="busy || selectedId === auth.user?.id" @click="save">Сохранить доступ</button>
    </template>
  </section>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useAuthStore } from '../stores/auth'
import { createUser, listUsers, saveAccess, type AccessUser } from '../api/users'
import { listReferences } from '../api/references'
const auth = useAuthStore()
const users = ref<AccessUser[]>([]), orgs = ref<{ id: number; name: string }[]>([])
const selectedId = ref(0), username = ref(''), password = ref(''), role = ref('viewer'), unrestricted = ref(false)
const allowed = ref<number[]>([]), busy = ref(false), error = ref(''), message = ref('')
function selectUser() {
  const user = users.value.find(row => row.id === selectedId.value)
  role.value = user?.role ?? 'viewer'; unrestricted.value = user?.organization_ids === null
  allowed.value = [...(user?.organization_ids ?? [])]; message.value = ''; error.value = ''
}
async function load() {
  users.value = (await listUsers()).data
  const organizations: { id: number; name: string }[] = []
  for (let page = 1; ; page++) {
    const result = await listReferences('organizations', { page, page_size: 50 })
    organizations.push(...result.data as { id: number; name: string }[])
    if (page >= (result.pagination?.pages ?? 1)) break
  }
  orgs.value = organizations
}
async function save() {
  busy.value = true; error.value = ''; message.value = ''
  try {
    const ids = unrestricted.value ? null : allowed.value
    const result = selectedId.value ? await saveAccess(selectedId.value, role.value, ids)
      : await createUser(username.value, password.value, role.value, ids)
    selectedId.value = result.data.id; password.value = ''; await load(); message.value = 'Доступ сохранен'
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { busy.value = false }
}
onMounted(async () => { if (auth.canManageAccess) { try { await load() } catch (e) { error.value = String(e) } } })
</script>
<style scoped>
.access-page { padding: 1.25rem; display: grid; gap: 1rem; max-width: 48rem; }
label { display: flex; gap: .6rem; align-items: center; } fieldset { display: grid; gap: .5rem; }
</style>
