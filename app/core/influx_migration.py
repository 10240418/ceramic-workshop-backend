# ============================================================
# 文件说明: influx_migration.py - InfluxDB 自动迁移管理
# ============================================================
# 方法列表:
# 1. check_and_create_bucket()     - 检查并创建 Bucket
# 2. create_retention_policies()   - 创建保留策略
# 3. create_continuous_queries()   - 创建连续查询（聚合）
# 4. verify_schema()               - 验证 Schema 结构
# 5. auto_migrate()                - 自动迁移（启动时调用）
# ============================================================

import logging
import os
from datetime import timedelta

from influxdb_client import InfluxDBClient, BucketRetentionRules
from influxdb_client.client.write_api import SYNCHRONOUS
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

from app.core.influx_schema import (
    ALL_SCHEMAS,
    RetentionPeriod,
    get_schema_summary
)


class InfluxDBMigration:
    """InfluxDB 迁移管理器
    
    自动创建和管理 InfluxDB 的 Schema 结构：
    - Bucket（数据库）
    - Retention Policy（保留策略）
    - Continuous Query（连续查询/聚合）
    """
    
    def __init__(
        self,
        url: str = None,
        token: str = None,
        org: str = None,
        bucket: str = None
    ):
        """初始化迁移管理器
        
        Args:
            url: InfluxDB URL（默认从环境变量读取）
            token: 认证Token
            org: 组织名称
            bucket: 主 Bucket 名称
        """
        self.url = url or os.getenv("INFLUX_URL", "http://localhost:8086")
        self.token = token or os.getenv("INFLUX_TOKEN", "ceramic-workshop-token")
        self.org = org or os.getenv("INFLUX_ORG", "ceramic-workshop")
        self.bucket = bucket or os.getenv("INFLUX_BUCKET", "sensor_data")
        
        self.client = None
    
    def connect(self) -> bool:
        """连接到 InfluxDB
        
        # 1, 连接失败时确保资源正确释放
        """
        try:
            self.client = InfluxDBClient(
                url=self.url,
                token=self.token,
                org=self.org
            )
            # 测试连接
            self.client.ping()
            return True
        except Exception as e:
            # 1, 连接失败时关闭已创建的 client，防止泄漏
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None
            logger.error("[Migration] InfluxDB 连接失败: %s", e, exc_info=True)
            return False
    
    def disconnect(self) -> None:
        """断开连接"""
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None
    
    # ------------------------------------------------------------
    # 1. check_and_create_bucket() - 检查并创建 Bucket
    # ------------------------------------------------------------
    def check_and_create_bucket(self) -> bool:
        """检查并创建主 Bucket（如果不存在）
        
        Returns:
            bool: 是否成功
        """
        try:
            buckets_api = self.client.buckets_api()
            
            # 检查 Bucket 是否存在
            existing_bucket = buckets_api.find_bucket_by_name(self.bucket)
            
            if existing_bucket:
                logger.info("[Migration] Bucket 已存在: %s (永久保留)", self.bucket)
                return True
            
            # 创建新 Bucket（永久保留，无过期策略）
            logger.info("[Migration] 创建 Bucket: %s (永久保留)", self.bucket)
            
            buckets_api.create_bucket(
                bucket_name=self.bucket,
                org=self.org
                # 不设置 retention_rules 表示永久保留
            )
            
            logger.info("[Migration] Bucket 创建成功: %s (永久保留)", self.bucket)
            return True
            
        except Exception as e:
            logger.error("[Migration] Bucket 创建失败: %s", e, exc_info=True)
            return False
    
    # ------------------------------------------------------------
    # 2. create_retention_policies() - 创建保留策略（已取消，永久保留）
    # ------------------------------------------------------------
    def create_retention_policies(self) -> bool:
        """创建保留策略（当前配置为永久保留，此方法已简化）
        
        注意：所有数据均设置为永久保留，无自动过期策略
        
        Returns:
            bool: 是否成功
        """
        logger.info("[Migration] 所有数据已配置为永久保留, 无需创建额外保留策略")
        return True
    
    # ------------------------------------------------------------
    # 3. create_continuous_queries() - 创建连续查询（已取消）
    # ------------------------------------------------------------
    def create_continuous_queries(self) -> bool:
        """创建连续查询（当前已取消数据聚合）
        
        注意：由于数据永久保留，暂不需要数据聚合任务
        如需后续添加聚合，可在此扩展
        
        Returns:
            bool: 是否成功
        """
        logger.info("[Migration] 数据永久保留, 暂不创建聚合任务")
        return True
    
    # ------------------------------------------------------------
    # 4. verify_schema() - 验证 Schema 结构
    # ------------------------------------------------------------
    def verify_schema(self) -> bool:
        """验证所有定义的 Measurement 是否正常
        
        Returns:
            bool: 是否验证通过
        """
        try:
            logger.info("[Migration] 验证 Schema 定义...")
            
            summary = get_schema_summary()
            total = summary['total_measurements']
            logger.info("[Migration] 共定义 %s 个 Measurements", total)
            
            # 按分类显示
            categories = {
                "窑炉设备": ["roller_kiln_temp", "roller_kiln_energy", "rotary_kiln_temp", 
                          "rotary_kiln_energy", "rotary_kiln_feed", "rotary_kiln_hopper"],
                "SCR设备": ["scr_fan", "scr_pump", "scr_gas"],
                "系统功能": ["alarms", "production_stats"],
                "模块化数据": ["module_data"],
            }
            
            for category, measurement_names in categories.items():
                logger.info("[Migration] [%s]", category)
                for m in summary['measurements']:
                    if m['name'] in measurement_names:
                        tags_str = f"{m['tags_count']} tags" if m['tags_count'] > 0 else "无tags"
                        logger.info("[Migration]   %s | %s fields, %s", m['name'], m['fields_count'], tags_str)
            
            logger.info("[Migration] Schema 验证通过 (共 %s 个表)", total)
            return True
            
        except Exception as e:
            logger.error("[Migration] Schema 验证失败: %s", e, exc_info=True)
            return False
    
    # ------------------------------------------------------------
    # 5. auto_migrate() - 自动迁移（启动时调用）
    # ------------------------------------------------------------
    def auto_migrate(self) -> bool:
        """自动执行所有迁移步骤
        
        启动时调用，确保 InfluxDB 结构正确
        
        Returns:
            bool: 迁移是否成功
        """
        logger.info("[Migration] " + "=" * 50)
        logger.info("[Migration] InfluxDB 自动迁移")
        logger.info("[Migration] " + "=" * 50)
        
        # 1. 连接
        logger.info("[Migration] [1/5] 连接 InfluxDB...")
        if not self.connect():
            return False
        logger.info("[Migration] 连接成功")
        
        # 2. 创建主 Bucket
        logger.info("[Migration] [2/5] 检查并创建主 Bucket...")
        if not self.check_and_create_bucket():
            return False
        
        # 3. 创建保留策略 Bucket
        logger.info("[Migration] [3/5] 创建保留策略...")
        if not self.create_retention_policies():
            logger.warning("[Migration] 保留策略创建失败, 使用默认策略")
        
        # 4. 创建连续查询（可选）
        logger.info("[Migration] [4/5] 创建连续查询...")
        self.create_continuous_queries()
        
        # 5. 验证 Schema
        logger.info("[Migration] [5/5] 验证 Schema...")
        if not self.verify_schema():
            return False
        
        logger.info("[Migration] " + "=" * 50)
        logger.info("[Migration] InfluxDB 迁移完成")
        logger.info("[Migration] " + "=" * 50)
        
        self.disconnect()
        return True


# ============================================================
# 启动时自动迁移函数
# ============================================================
def auto_migrate_on_startup() -> bool:
    """启动时自动执行 InfluxDB 迁移
    
    在 main.py 的 lifespan 中调用
    
    Returns:
        bool: 迁移是否成功
    """
    try:
        migration = InfluxDBMigration()
        return migration.auto_migrate()
    except Exception as e:
        logger.error("[Migration] InfluxDB 自动迁移失败: %s", e, exc_info=True)
        return False


# ============================================================
# 命令行工具
# ============================================================
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        # 手动执行迁移
        migration = InfluxDBMigration()
        success = migration.auto_migrate()
        sys.exit(0 if success else 1)
    else:
        print("""
╔══════════════════════════════════════════════════════════════════╗
║           InfluxDB 迁移管理工具                                   ║
╚══════════════════════════════════════════════════════════════════╝

使用方法:
  python -m app.core.influx_migration migrate    # 执行迁移

功能:
  1. 自动创建 Bucket（数据库）
  2. 配置保留策略（7天/90天/2年）
  3. 创建连续查询（数据聚合）
  4. 验证 Schema 定义

配置:
  通过环境变量配置：
  - INFLUX_URL=http://localhost:8086
  - INFLUX_TOKEN=ceramic-workshop-token
  - INFLUX_ORG=ceramic-workshop
  - INFLUX_BUCKET=sensor_data
        """)
