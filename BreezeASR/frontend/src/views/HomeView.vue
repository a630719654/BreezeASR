<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { createJob } from "../api/jobs";
import { deleteTranscript, listTranscripts } from "../api/transcripts";
import AppTopbar from "../components/AppTopbar.vue";
import TranscriptCard from "../components/TranscriptCard.vue";
import { useAuth } from "../composables/useAuth";
import { useConfirm } from "../composables/useConfirm";

const router = useRouter();
const { state } = useAuth();
const { askConfirm } = useConfirm();

const file = ref(null);
const status = ref("");
const submitting = ref(false);
const history = ref([]);
const historyError = ref("");
const openRecord = ref(null);

function onFileChange(event) {
  file.value = event.target.files && event.target.files[0] ? event.target.files[0] : null;
}

async function loadHistory() {
  try {
    history.value = await listTranscripts();
    historyError.value = "";
  } catch (error) {
    if (error.status === 401) {
      await router.push("/login");
      return;
    }
    history.value = [];
    historyError.value = "讀不到已保存的逐字稿。";
  }
}

async function onSubmit() {
  if (!file.value) {
    status.value = "請先選擇音檔。";
    return;
  }
  submitting.value = true;
  status.value = "正在建立辨識工作。";
  try {
    const job = await createJob(file.value);
    await router.push({ path: "/progress", query: { job: job.id } });
  } catch (error) {
    if (error.status === 401) {
      await router.push("/login");
      return;
    }
    status.value = error.message || "無法開始辨識";
    submitting.value = false;
  }
}

async function onDelete(item) {
  const confirmed = await askConfirm({
    title: "確定刪除這筆逐字稿？",
    body: `${item.source_filename} 會從 JSON 紀錄裡移除，刪除後無法復原。`,
    confirmLabel: "確定刪除",
  });
  if (!confirmed) {
    return;
  }
  try {
    await deleteTranscript(item.id);
    if (openRecord.value && openRecord.value.id === item.id) {
      openRecord.value = null;
    }
    status.value = "已刪除逐字稿。";
    await loadHistory();
  } catch (error) {
    if (error.status === 401) {
      await router.push("/login");
      return;
    }
    status.value = error.message || "刪除失敗";
  }
}

onMounted(loadHistory);
</script>

<template>
  <div class="app-shell">
    <AppTopbar :user="state.user" />
    <div class="stack">
      <header class="page-header">
        <p class="eyebrow">本地語音辨識</p>
        <h1>Breeze-ASR-26</h1>
        <p class="lead">本服務提供本地語音辨識功能，請將音檔上傳進行辨識，辨識完成後可查看逐字稿，逐字稿只屬於目前登入的帳號。</p>
      </header>

      <form id="upload-form" class="card" @submit.prevent="onSubmit">
        <label for="audio-file">音檔</label>
        <input id="audio-file" name="file" type="file" accept=".wav,.mp3,.m4a,.flac,.ogg,.webm,.mp4,.aac,audio/*,video/mp4,video/webm" @change="onFileChange">
        <p class="hint">支援 wav、mp3、m4a、flac、ogg、webm、mp4、aac，上限 200 MB。</p>
        <button id="submit" type="submit" :disabled="submitting">開始辨識</button>
        <p id="status" role="status">{{ status }}</p>
      </form>

      <TranscriptCard v-if="openRecord" :record="openRecord" closable @close="openRecord = null" />

      <section class="card">
        <h2>已保存的逐字稿</h2>
        <div id="history">
          <p v-if="historyError" class="empty">{{ historyError }}</p>
          <p v-else-if="history.length === 0" class="empty">還沒有逐字稿。</p>
          <ul v-else>
            <li v-for="item in history" :key="item.id" class="history-row">
              <button type="button" class="open" @click="openRecord = item; status = '這筆逐字稿讀自 JSON。'">
                {{ item.source_filename }} · {{ item.created_at }}
              </button>
              <button type="button" class="danger compact" @click="onDelete(item)">刪除</button>
            </li>
          </ul>
        </div>
      </section>
    </div>
  </div>
</template>
