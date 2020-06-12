# -*- coding: utf-8 -*-
from flask import current_app
from sqlalchemy import false, or_
from datetime import timedelta, datetime
from .register_ext import celery, db, conn


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
# if __name__ == '__main__':
#     from tickets import create_app
#
#     app = create_app()
#     with app.app_context():
#         change_activity_status()
