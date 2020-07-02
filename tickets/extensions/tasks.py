# -*- coding: utf-8 -*-
from flask import current_app
from sqlalchemy import false
from datetime import timedelta
from .register_ext import celery, db, conn
from ..config.enums import ProductStatus
from ..models import Product

# 图片下载格式配置文件
contenttype_config = {
    r'image/jpeg': r'.jpg',
    r'image/pnetvue': r'.net',
    r'image/tiff': r'.tif',
    r'image/fax': r'.fax',
    r'image/gif': r'.gif',
    r'image/png': r'.png',
    r'image/vnd.rn-realpix': r'.rp',
    r'image/vnd.wap.wbmp': r'.wbmp',
}


def add_async_task(func, start_time, func_args, conn_id=None, queue='high_priority'):
    """
    添加异步任务
    func: 任务方法名 function
    start_time: 任务执行时间 datetime
    func_args: 函数所需参数 tuple
    conn_id: 要存入redis的key
    """
    task_id = func.apply_async(args=func_args, eta=start_time - timedelta(hours=8), queue=queue)
    connid = conn_id if conn_id else str(func_args[0])
    current_app.logger.info(f'add async task: func_args:{func_args} | connid: {conn_id}, task_id: {task_id}')
    conn.set(connid, str(task_id))


def cancel_async_task(conn_id):
    """
    取消已存在的异步任务
    conn_id: 存在于redis的key
    """
    exist_task_id = conn.get(conn_id)
    if exist_task_id:
        exist_task_id = str(exist_task_id, encoding='utf-8')
        celery.AsyncResult(exist_task_id).revoke()
        conn.delete(conn_id)
        current_app.logger.info(f'取消任务成功 task_id:{exist_task_id}')


@celery.task()
def auto_cancle_order(omid):
    try:
        # for omid in omids:
        from tickets.control.COrder import COrder
        from tickets.models import OrderMain
        from tickets.config.enums import OrderStatus
        order_main = OrderMain.query.filter(OrderMain.isdelete == false(),
                                            OrderMain.OMstatus == OrderStatus.wait_pay.value,
                                            OrderMain.OMid == omid).first()
        if not order_main:
            current_app.logger.info('订单已支付或已取消')
            return
        current_app.logger.info('订单自动取消{}'.format(dict(order_main)))
        corder = COrder()
        corder._cancle(order_main)
    except Exception as e:
        current_app.logger.error('取消订单出错： {}'.format(e))
    finally:
        current_app.logger.info('取消订单任务结束')



@celery.task()
def start_product(prid):
    current_app.logger.info('修改限时商品为开始状态 prid {}'.format(prid))
    try:
        with db.auto_commit():
            product = Product.query.filter(Product.isdelete == false(), Product.PRid == prid).first()
            if not product:
                current_app.logger.error(">>> 未找到该限时商品 <<<")
                return
            if not product.PRtimeLimeted:
                current_app.logger.error(">>> 该商品非限时 <<<")
                return
            if product.PRstatus != ProductStatus.ready.value:
                current_app.logger.error(">>> 该商品状态异常, prstatus: {} <<<".format(product.PRstatus))
                return
            product.PRstatus = ProductStatus.active.value
        connid = 'start_product{}'.format(product.PRid)
        conn_value = conn.get(connid)
        if conn_value:
            current_app.logger.info('exist start product conn:{}/{}'.format(connid, str(conn_value), encoding='utf-8'))
            conn.delete(connid)
    except Exception as e:
        current_app.logger.error("限时商品修改为开始时出错 : {} <<<".format(e))
    finally:
        current_app.logger.info('限时商品修改为开始任务结束 prid {}'.format(prid))


@celery.task()
def end_product(prid):
    current_app.logger.info('修改限时商品为结束 prid {}'.format(prid))
    from tickets.control.COrder import COrder
    try:
        with db.auto_commit():
            product = Product.query.filter(Product.isdelete == false(), Product.PRid == prid).first()
            if not product:
                current_app.logger.error(">>> 未找到此商品 <<<")
                return
            if product.PRstatus != ProductStatus.active.value:
                current_app.logger.error(">>> 该限时商品状态异常, prstatus: {} <<<".format(product.PRstatus))
                return
            # 开奖 + 未中奖 改订单状态
            COrder().product_score_award(product)
            product.PRstatus = ProductStatus.over.value
    except Exception as e:
        current_app.logger.error("该票修改为结束时出错 : {} <<<".format(e))
    finally:
        current_app.logger.info('修改抢票为结束任务完成 prid {}'.format(prid))

# if __name__ == '__main__':
#     from tickets import create_app
#
#     app = create_app()
#     with app.app_context():
#         change_activity_status()
