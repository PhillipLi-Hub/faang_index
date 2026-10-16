# Deploy on Render's free plan

The included render.yaml configures a free Python web service, health check and randomly generated refresh token. No market-data key is needed to deploy the demo. A Render account and a GitHub repository containing this project's source files are needed.

1. Create an empty GitHub repository named `faang-index-api` at https://github.com/new . A private repository is fine if you grant Render access.
2. Upload the contents of this project's deployment ZIP **after extracting it** into that repository's root. Do not upload the ZIP itself, `.venv`, `data`, `.env`, or API keys. Commit the uploaded files. The root should contain `src/`, `pyproject.toml`, `requirements.txt` and `render.yaml`; the application entry point is `src/faang_index_api/main.py`.
3. Sign in at https://dashboard.render.com/ and choose **New → Blueprint**. Connect GitHub and select that repository. Render reads `render.yaml` from its root.
4. Review that the service uses the **Free** plan and deploy it. No paid disk, database or custom domain is configured.
5. After deployment succeeds, Render displays the actual HTTPS `onrender.com` URL. Open `<that-url>/docs`, then try **GET /api/demo → Try it out → Execute**. The service name may need a suffix for uniqueness; use the returned URL, not an assumed hostname.

For manual **New → Web Service** creation instead, choose Python 3, Free plan, build command `pip install -r requirements.txt`, start command `uvicorn faang_index_api.main:app --host 0.0.0.0 --port $PORT --workers 1`, health path `/health`, and environment `PYTHON_VERSION=3.12.8`, `REQUIRE_REFRESH_TOKEN=true`, plus a long random `REFRESH_TOKEN` stored as a secret. Never put secrets in the repository.

## Enable real market data later

In Render's service **Environment** settings, add `FMP_API_KEY` with your entitled provider key and restart/redeploy. Keep `REFRESH_TOKEN` secret. In `/docs`, click **Authorize** and enter the `REFRESH_TOKEN` value from Render's environment settings. That value is different from your FMP key. Then POST `/api/refresh`, poll `/api/refresh/status`, and GET `/api/index` after completion. Public visitors can read the resulting index; confirm the provider allows public redistribution before enabling live data. Unauthenticated users cannot start quota-consuming refreshes.

## Free-plan limitations

Render's free service sleeps after 15 minutes without traffic and takes time to wake up. Local files are ephemeral: index output and provider cache can disappear on restart, redeployment or spin-down. Long refresh jobs can be interrupted. This configuration is appropriate for a demo; it does not provide durable daily index hosting or a scheduled refresh. A durable store and reliable background processing would be a separate change. Losing the cache can cause another full set of provider calls.

Deploying there runs the app on Render, so your PC and Start.ps1 can be off. No custom `.com` registration is needed. The free hosting address does not make FMP market data free.

Official instructions: https://render.com/docs/deploy-fastapi , https://render.com/docs/infrastructure-as-code , https://render.com/docs/free
