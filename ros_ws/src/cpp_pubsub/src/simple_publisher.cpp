#include <chrono>
#include <memory>
#include <string>

#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/string.hpp>
#include <opencv2/opencv.hpp>
#include <cv_bridge/cv_bridge.hpp>
#include "sensor_msgs/msg/image.hpp"
#include <sensor_msgs/msg/compressed_image.hpp>
#include <thread>
#include <atomic>

using namespace std::chrono_literals;
using namespace cv;


class SimplePublisher : public rclcpp::Node
{
public:
  SimplePublisher()
  : Node("simple_publisher")
  {
    publisher_ = this->create_publisher<std_msgs::msg::String>("topic", 10);
    cv_publisher_ = this->create_publisher<sensor_msgs::msg::Image>("camera/mjpg", rclcpp::SensorDataQoS());
    jpeg_publisher_ = this->create_publisher<sensor_msgs::msg::CompressedImage>(
  "camera/image/compressed", rclcpp::SensorDataQoS());

    cap_.open(0, cv::CAP_V4L2);
    cap_.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M', 'J', 'P', 'G'));
    /*UDEN AT DECODE FRA MJPEG TIL RAW.*/
    cap_.set(cv::CAP_PROP_CONVERT_RGB, 0);   // <-- nøglen: rå bytes, ingen dekodning
    cap_.set(cv::CAP_PROP_FRAME_WIDTH, 640);
    cap_.set(cv::CAP_PROP_FRAME_HEIGHT, 480);
    cap_.set(cv::CAP_PROP_FPS, 30);
    cap_.set(cv::CAP_PROP_AUTO_EXPOSURE, 1);  // manual
    cap_.set(cv::CAP_PROP_EXPOSURE, 900);
    cap_.set(cv::CAP_PROP_BUFFERSIZE, 1);  // hold frames friske

    if (!cap_.isOpened()) {
      RCLCPP_ERROR(this->get_logger(), "Kunne ikke åbne kamera");
      throw std::runtime_error("Camera open failed");
    }

    RCLCPP_INFO(this->get_logger(), "Kamera: %.0fx%.0f @ %.0f fps",
                cap_.get(cv::CAP_PROP_FRAME_WIDTH),
                cap_.get(cv::CAP_PROP_FRAME_HEIGHT),
                cap_.get(cv::CAP_PROP_FPS));

    // capture_thread_ = std::thread([this]() {
    //   cv::Mat frame;
    //   while (rclcpp::ok() && running_) {
    //     if (cap_.read(frame) && !frame.empty()) {
    //       auto msg = cv_bridge::CvImage(std_msgs::msg::Header(), "bgr8", frame).toImageMsg();
    //       msg->header.stamp = this->now();
    //       cv_publisher_->publish(*msg);
    //       static int count = 0;
    //       static auto t0 = std::chrono::steady_clock::now();
    //       if (++count % 30 == 0) {
    //         auto dt = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    //         RCLCPP_INFO(this->get_logger(), "Publish-rate: %.1f fps", 30.0 / dt);
    //         t0 = std::chrono::steady_clock::now();
    //     }
    //   }
    //   }
    // });

    capture_thread_ = std::thread([this]() {
      cv::Mat buf;
      while (rclcpp::ok() && running_) {
        if (cap_.read(buf) && !buf.empty()) {
          auto msg = sensor_msgs::msg::CompressedImage();
          msg.header.stamp = this->now();
          msg.header.frame_id = "camera";
          msg.format = "jpeg";
          msg.data.assign(buf.data, buf.data + buf.total() * buf.elemSize());
          jpeg_publisher_->publish(std::move(msg));
          RCLCPP_INFO(this->get_logger(), "Buffer: %zu bytes, dims: %dx%d",
          buf.total() * buf.elemSize(), buf.cols, buf.rows);
        }
      }
    });
  }

  ~SimplePublisher() override {
  running_ = false;
  if (capture_thread_.joinable()) {
    capture_thread_.join();
  }
}

private:
  std::thread capture_thread_;
  std::atomic<bool> running_{true};
  cv::VideoCapture cap_;
  rclcpp::TimerBase::SharedPtr timer_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr publisher_;
  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr cv_publisher_;
  rclcpp::Publisher<sensor_msgs::msg::CompressedImage>::SharedPtr jpeg_publisher_;
  cv_bridge::CvImagePtr cv_ptr;
};

// int main(int argc, char * argv[])
// {
//   rclcpp::init(argc, argv);
//   rclcpp::spin(std::make_shared<SimplePublisher>());
//   rclcpp::shutdown();
//   return 0;
// }

int main(int argc, char** argv) {
  rclcpp::init(argc, argv);
  {
    auto node = std::make_shared<SimplePublisher>();
    rclcpp::spin(node);
  }  // node destrueres her, tråden joines
  rclcpp::shutdown();
  return 0;
}

//Dette er åbenbart en flaskehals når man skal køre med højere opløsning og framerate. Man kan sætte miljøvariablen FASTDDS_BUILTIN_TRANSPORTS=UDPv4 for at bruge UDP i stedet for TCP, hvilket kan give bedre performance.
// export FASTDDS_BUILTIN_TRANSPORTS=UDPv4