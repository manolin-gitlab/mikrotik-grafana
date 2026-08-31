# Monitoreo MikroTik → Prometheus → Grafana

Stack Docker Compose para monitorear un MikroTik (pensado para correr en una
Raspberry o cualquier host con Docker). Dos exporters alimentan Prometheus:

- **mktxp**: recursos del router (CPU, RAM, disco, salud, temperatura), tráfico
  por interfaz, DHCP, wireless. El histórico lo guarda Prometheus.
- **topflows-exporter** (propio): consulta `/ip/firewall/connection` en el
  MikroTik y publica los top N destinos por tráfico, para saber a dónde van las
  peticiones que pasan por el router.

## Seguridad primero

- **Nunca commitear credenciales.** `.env` y `mktxp-config/mktxp.conf` están en
  `.gitignore`; los archivos versionados son solo `.example` con placeholders.
- **Router remoto ⇒ API-SSL.** La API plana (8728) manda usuario y password en
  texto claro. Si el router no está en la misma LAN/VPN, usar `api-ssl` (8729)
  con `MTK_USE_SSL=true` y `use_ssl = True` en `mktxp.conf`.
- **Restringir la API en el router** a la IP de esta máquina (ver abajo).
- Prometheus y los exporters **no se exponen a la red**: Prometheus solo
  escucha en `127.0.0.1:9090` del host y los exporters solo en la red interna
  de Docker. Hacia afuera solo se publica Grafana (`:3000`), que sí tiene login.

## 1. Preparar el MikroTik

Crear un usuario de solo lectura dedicado (no usar el admin):

```
/user group add name=mktxp_group policy=api,read
/user add name=mktxp_user group=mktxp_group password=ELEGIR_PASSWORD_FUERTE
```

Habilitar la API y restringirla a la IP de la máquina que monitorea:

```
/ip service set api disabled=no address=IP_DE_ESTA_MAQUINA/32
```

Si el router es remoto, mejor API-SSL (necesita un certificado en el router):

```
/ip service set api-ssl disabled=no address=IP_DE_ESTA_MAQUINA/32
```

## 2. Configurar

```
cp .env.example .env
cp mktxp-config/mktxp.conf.example mktxp-config/mktxp.conf
```

- `.env`: IP del router, usuario, password y la password de admin de Grafana
  (obligatoria: sin ella el stack no arranca).
- `mktxp-config/mktxp.conf`: misma IP/usuario/password en `[Router-Principal]`
  (se pueden agregar más routers, una sección por cada uno).

Ambos archivos quedan fuera de git.

## 3. Levantar

```
docker compose up -d --build
```

- Grafana: `http://<host>:3000` (user `admin`, password del `.env`)
- Prometheus: solo local. Desde otra PC: `ssh -L 9090:localhost:9090 <host>` y
  abrir `http://localhost:9090`.

## 4. Dashboards

- **MikroTik Top Flows** ya queda provisto automáticamente en Grafana: tráfico
  por destino (bps), conexiones activas y tabla de top destinos.
- Para los recursos del router, importar el dashboard comunitario de mktxp
  (Dashboards → Import): ID `24875` (MikroTik Router Monitoring) o `10950`
  (Mikrotik Exporter), eligiendo el datasource "Prometheus".

## Métricas del topflows-exporter

| Métrica | Tipo | Significado |
|---|---|---|
| `mikrotik_topflows_bps` | gauge | Bytes/segundo hacia cada destino durante el último intervalo (deltas reales entre muestreos). Es la métrica correcta para graficar en el tiempo (`* 8` para bps). |
| `mikrotik_connection_bytes` | gauge | Bytes acumulados de las conexiones vivas en el instante del muestreo. Es una foto: sirve para la tabla de "top talkers ahora", no para históricos. |
| `mikrotik_active_connections` | gauge | Tamaño de la tabla de conexiones del router. |

## Rendimiento

El exporter lista la tabla de conexiones completa cada `INTERVAL` segundos. En
un router de borde con pocas mil conexiones es despreciable, pero en un core
con CGNAT (cientos de miles de entradas) serializar eso por API castiga el CPU
del router: subir `INTERVAL` a 60+ o usar Traffic Flow/NetFlow en su lugar.

## Retención de histórico

Prometheus queda con `--storage.tsdb.retention.time=180d` (6 meses) en el
`docker-compose.yml`. Ajustar según el disco disponible.
