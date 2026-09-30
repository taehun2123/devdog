import DefaultTheme from 'vitepress/theme';
import { h } from 'vue';
import SourceInfo from './SourceInfo.vue';
import MermaidDiagram from './MermaidDiagram.vue';
// 한글 본문 가독성: IBM Plex Sans KR(OFL-1.1). 사용하는 굵기만 포함
import '@fontsource/ibm-plex-sans-kr/400.css';
import '@fontsource/ibm-plex-sans-kr/500.css';
import '@fontsource/ibm-plex-sans-kr/600.css';
import '@fontsource/ibm-plex-sans-kr/700.css';
import './style.css';
import './custom.css';
export default {
  extends: DefaultTheme,
  Layout: () => h(DefaultTheme.Layout, null, { 'doc-after': () => h(SourceInfo) }),
  enhanceApp({ app }) {
    app.component('MermaidDiagram', MermaidDiagram);
  }
};
