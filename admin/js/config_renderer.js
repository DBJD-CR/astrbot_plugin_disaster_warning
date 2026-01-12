const ConfigRenderer = {
    name: 'ConfigRenderer',
    props: {
        schema: {
            type: Object,
            required: true
        },
        config: {
            type: Object,
            required: true
        },
        prefix: {
            type: String,
            default: ''
        },
        depth: {
            type: Number,
            default: 0
        }
    },
    data() {
        return {
            expandedSections: new Set()
        };
    },
    methods: {
        toggleSection(key) {
            if (this.expandedSections.has(key)) {
                this.expandedSections.delete(key);
            } else {
                this.expandedSections.add(key);
            }
            // Force update to reflect changes (Set is not reactive by default in Vue 2/3 basic usage sometimes, but usually ok)
            // In Vue 3 reactive() Set works, but here we are in options API data(), simple reassignment or new Set might be needed if reactivity fails.
            // Using a new Set to trigger reactivity safely.
            this.expandedSections = new Set(this.expandedSections);
        },
        isSectionExpanded(key) {
            return this.expandedSections.has(key);
        },
        getFieldKey(key) {
            return this.prefix ? `${this.prefix}.${key}` : key;
        },
        formatList(val) {
            return Array.isArray(val) ? val.join(', ') : '';
        },
        updateList(key, event) {
            const val = event.target.value;
            this.config[key] = val.split(',').map(s => s.trim()).filter(s => s);
        }
    },
    template: `
    <div>
        <div v-if="!config" style="padding:16px;color:red;">Error: Config object is missing via ConfigRenderer</div>
        <template v-else v-for="(item, key) in schema" :key="key">
            <!-- Object type - collapsible section -->
            <div v-if="item.type === 'object' && item.items" 
                 class="settings-section"
                 :class="{ collapsed: !isSectionExpanded(getFieldKey(key)) }" 
                 :data-key="getFieldKey(key)"
                 :style="{ animationDelay: (depth * 0.05) + 's' }">
                
                <div class="section-header" @click="toggleSection(getFieldKey(key))">
                    <div>
                        <span class="section-title">{{ item.description || key }}</span>
                        <div v-if="item.hint" class="section-hint" style="font-size:0.8em;color:var(--md-sys-color-on-surface-variant);">
                            {{ item.hint }}
                        </div>
                    </div>
                    <div style="display:flex;align-items:center;gap:12px;">
                        <!-- Show enabled toggle if exists in items -->
                        <!-- GUARD: Check if config[key] exists -->
                        <template v-if="config[key] && item.items.enabled && item.items.enabled.type === 'bool'">
                            <div class="section-summary" style="display:flex;align-items:center;gap:8px;">
                                <span class="section-summary-label">{{ config[key].enabled ? 'On' : 'Off' }}</span>
                                <label class="switch" @click.stop>
                                    <input type="checkbox" v-model="config[key].enabled">
                                    <span class="slider round"></span>
                                </label>
                            </div>
                        </template>
                        <span class="section-toggle">▼</span>
                    </div>
                </div>

                <div class="section-body">
                    <!-- Recursively render children -->
                    <!-- GUARD: Only render if config[key] is an object -->
                    <div v-if="config[key] && typeof config[key] === 'object'">
                         <config-renderer 
                            :schema="item.items" 
                            :config="config[key]" 
                            :prefix="getFieldKey(key)"
                            :depth="depth + 1">
                         </config-renderer>
                    </div>
                    <div v-else class="form-hint" style="color:red;padding:8px;">
                        Configuration missing for section: {{ key }}
                    </div>
                </div>
            </div>

            <!-- Simple Fields -->
            <div v-else-if="key !== 'enabled'" class="form-group">
                <div class="form-label-row">
                    <label>{{ item.description || key }}</label>
                    <div class="form-control-wrapper">
                        
                        <!-- Check if config exists for this key to avoid v-model errors? -->
                        <!-- Actually v-model on config[key] works if config is object. -->
                        
                        <!-- Boolean -->
                        <label v-if="item.type === 'bool'" class="switch">
                            <input type="checkbox" v-model="config[key]">
                            <span class="slider round"></span>
                        </label>

                        <!-- Select -->
                        <select v-else-if="item.options" class="form-control" v-model="config[key]">
                            <option v-for="opt in item.options" :key="opt" :value="opt">
                                {{ opt }}
                            </option>
                        </select>

                        <!-- Slider (Int/Float) -->
                        <div v-else-if="item.slider" class="range-wrapper">
                            <input type="range" 
                                   v-model.number="config[key]" 
                                   :min="item.slider.min" 
                                   :max="item.slider.max" 
                                   :step="item.slider.step">
                            <span class="range-val">{{ config[key] }}</span>
                        </div>

                        <!-- Number -->
                        <input v-else-if="item.type === 'int' || item.type === 'float'" 
                               type="number" 
                               class="form-control" 
                               v-model.number="config[key]"
                               :step="item.type === 'float' ? '0.1' : '1'">

                        <!-- List -->
                        <input v-else-if="item.type === 'list'"
                               type="text"
                               class="form-control"
                               :value="formatList(config[key])"
                               @input="updateList(key, $event)"
                               placeholder="用逗号分隔">

                        <!-- Text -->
                        <input v-else 
                               type="text" 
                               class="form-control" 
                               v-model="config[key]">

                    </div>
                </div>
                <div v-if="item.hint" class="form-hint" style="font-size:0.8em;color:var(--md-sys-color-on-surface-variant);">
                    {{ item.hint }}
                </div>
            </div>
        </template>
    </div>
    `
};

// Export for usage
window.ConfigRenderer = ConfigRenderer;
