/// <reference types="vite/client" />

declare module "*.svg?no-inline" {
  const src: string;
  export default src;
}
