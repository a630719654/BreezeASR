<script setup>
import { nextTick, ref, watch } from "vue";
import { formatTranscriptDate, transcriptTitle } from "../composables/useTranscriptFilters";
import MarkdownBody from "./MarkdownBody.vue";

const props = defineProps({
  record: { type: Object, default: null },
});

const emit = defineEmits(["close", "title-change", "add-tag", "tags-change"]);
const dialogEl = ref(null);
const titleInput = ref(null);
const editingTitle = ref(false);
const titleDraft = ref("");
const titleError = ref("");

watch(
  () => props.record,
  async (record) => {
    await nextTick();
    const el = dialogEl.value;
    if (!el) {
      return;
    }
    if (record) {
      if (!el.open) {
        el.showModal();
      }
      return;
    }
    editingTitle.value = false;
    titleError.value = "";
    if (el.open) {
      el.close();
    }
  },
);

watch(
  () => props.record && props.record.id,
  () => {
    editingTitle.value = false;
    titleDraft.value = "";
    titleError.value = "";
  },
);

async function startEditTitle() {
  titleDraft.value = transcriptTitle(props.record);
  titleError.value = "";
  editingTitle.value = true;
  await nextTick();
  titleInput.value?.focus();
  titleInput.value?.select();
}

function cancelEditTitle() {
  editingTitle.value = false;
  titleError.value = "";
}

function saveTitle() {
  const title = titleDraft.value.trim();
  if (!title) {
    titleError.value = "標題不能是空白";
    return;
  }
  emit("title-change", title);
  editingTitle.value = false;
  titleError.value = "";
}

function removeTag(tag) {
  emit(
    "tags-change",
    (props.record.tags || []).filter((value) => value !== tag),
  );
}
</script>

<template>
  <dialog
    ref="dialogEl"
    class="summary-dialog"
    @close="emit('close')"
  >
    <div class="section-head">
      <div v-if="record" class="summary-title-row">
        <form v-if="editingTitle" class="summary-title-form" @submit.prevent="saveTitle">
          <input
            ref="titleInput"
            v-model="titleDraft"
            type="text"
            maxlength="80"
            aria-label="會議標題"
            @keydown.esc.prevent="cancelEditTitle"
          >
        </form>
        <h2 v-else>{{ transcriptTitle(record) }}</h2>
        <button
          type="button"
          class="icon-btn ghost"
          :aria-label="editingTitle ? '儲存標題' : '編輯標題'"
          @click="editingTitle ? saveTitle() : startEditTitle()"
        >
          <svg v-if="editingTitle" class="icon" viewBox="0 0 24 24" aria-hidden="true">
            <path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="M5 12.5 10 17.5 19 7.5" />
          </svg>
          <svg v-else class="icon" viewBox="0 0 24 24" aria-hidden="true">
            <path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="M13.4 5.6 18.4 10.6M4 20l1.3-6.3L16.2 2.8a2.1 2.1 0 0 1 3 3L8.3 16.7 4 20Z" />
          </svg>
        </button>
      </div>
      <h2 v-else>會議記錄摘要</h2>
      <button type="button" class="ghost compact" @click="emit('close')">關閉</button>
    </div>
    <p v-if="titleError" class="error tag-add-error">{{ titleError }}</p>
    <p v-if="!record" class="empty">讀取中。</p>
    <template v-else>
      <div class="summary-tag-row">
        <svg class="icon tag-icon" viewBox="0 0 24 24" aria-hidden="true">
          <path
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
            d="M20.59 13.41 13.42 20.58a2 2 0 0 1-2.83 0L3 13V4h9l8.59 8.59a2 2 0 0 1 0 2.82Z"
          />
          <circle cx="7.5" cy="7.5" r="1.15" fill="currentColor" />
        </svg>
        <div class="tag-chip-row">
          <span v-for="tag in record.tags || []" :key="tag" class="tag-chip">
            {{ tag }}
            <button type="button" class="tag-remove" :aria-label="`移除標籤 ${tag}`" @click="removeTag(tag)">×</button>
          </span>
          <button
            v-if="(record.tags || []).length < 8"
            type="button"
            class="tag-chip summary-add-tag"
            @click="emit('add-tag')"
          >
            新增標籤
          </button>
        </div>
      </div>
      <p class="history-date">
        <svg class="icon calendar-icon" viewBox="0 0 24 24" aria-hidden="true">
          <rect x="3.5" y="5" width="17" height="15.5" rx="2" fill="none" stroke="currentColor" stroke-width="1.8" />
          <path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" d="M8 3.5v4M16 3.5v4M3.5 10h17" />
        </svg>
        {{ formatTranscriptDate(record.created_at) }}
      </p>
      <hr class="summary-dialog-rule">
      <MarkdownBody :source="record.summary || ''" />
    </template>
  </dialog>
</template>
