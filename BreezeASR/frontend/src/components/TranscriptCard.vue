<script setup>
defineProps({
  record: { type: Object, required: true },
  closable: { type: Boolean, default: false },
});

defineEmits(["close"]);
</script>

<template>
  <section id="result" class="card">
    <div class="section-head">
      <h2>逐字稿</h2>
      <button v-if="closable" id="close-result" type="button" class="ghost compact" @click="$emit('close')">
        關閉記錄
      </button>
    </div>
    <p id="result-text">{{ record.text || "（沒有辨識到文字）" }}</p>
    <dl>
      <div>
        <dt>來源檔名</dt>
        <dd id="result-filename">{{ record.source_filename }}</dd>
      </div>
      <div>
        <dt>時間</dt>
        <dd id="result-time">{{ record.created_at }}</dd>
      </div>
    </dl>
  </section>
</template>
