/*
 * QtSelfUpdateBridge.hxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#ifndef SELFUPDATE_QT_SELF_UPDATE_BRIDGE_HXX
#define SELFUPDATE_QT_SELF_UPDATE_BRIDGE_HXX

#include <QCoreApplication>
#include <QMetaObject>
#include <QObject>
#include <QPointer>
#include <functional>
#include <utility>
#include "SelfUpdateController.hxx"

namespace selfupdate {

inline void bindQtController(SelfUpdateController& controller,
                             QObject* receiver,
                             SelfUpdateController::StateCallback onStateChanged,
                             SelfUpdateController::QuitCallback onQuit = nullptr)
{
    QObject* target = receiver ? receiver : QCoreApplication::instance();
    QPointer<QObject> safeReceiver(target);

    controller.setUiDispatcher([safeReceiver](std::function<void()> task) {
        if (!safeReceiver) {
            return;
        }
        QMetaObject::invokeMethod(safeReceiver.data(),
                                  [safeReceiver, task = std::move(task)]() {
                                      if (safeReceiver) {
                                          task();
                                      }
                                  },
                                  Qt::QueuedConnection);
    });

    controller.setStateCallback(std::move(onStateChanged));

    if (onQuit) {
        controller.setQuitCallback(std::move(onQuit));
    } else {
        controller.setQuitCallback([]() {
            if (auto* app = QCoreApplication::instance()) {
                app->quit();
            }
        });
    }
}

} // namespace selfupdate

#endif // SELFUPDATE_QT_SELF_UPDATE_BRIDGE_HXX

/*
 * Local variables:
 * mode: C++
 * c-file-style: "BSD"
 * c-basic-offset: 4
 * tab-width: 4
 * indent-tabs-mode: nil
 * End:
 */
