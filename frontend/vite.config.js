import {defineConfig} from 'vite';
export default defineConfig({base:'/',build:{outDir:'../bookledger/frontend_dist',emptyOutDir:true},server:{port:5173,proxy:{'/api':'http://127.0.0.1:8787','/favicon.svg':'http://127.0.0.1:8787'}}});
