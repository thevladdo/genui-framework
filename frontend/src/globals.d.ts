// Side-effect CSS imports (import './styles/genui.css') have no type
// declarations by default. This keeps editors and tsc quiet.
declare module "*.css";
declare var process: { env?: { NODE_ENV?: string } } | undefined;
